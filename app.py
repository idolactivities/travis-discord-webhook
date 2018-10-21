import json
import logging

from flask import Flask, request, abort
import requests
import yaml


PAYLOAD_TITLE = "Build #{number} {status_message} - {repository[owner_name]}/{repository[name]}"
PAYLOAD_COMMIT_URL = "https://github.com/{repository[owner_name]}/{repository[name]}/commit/{commit}"


with open("config.yaml") as file:
    config = yaml.load(file)

DISCORD_WEBHOOK = config["discord_webhook"]
AUTHORIZED_OWNERS = config["authorized_owners"]
COLORS = config["colors"]


app = Flask(__name__)

@app.route("/notify", methods=["POST"])
def webhook():
    data = request.form["payload"]
    data = json.loads(data)

    if data["repository"]["owner_name"] not in AUTHORIZED_OWNERS:
        abort(401)

    # Force lower because yaml uses lower case
    result = data["status_message"].lower()

    color = COLORS[result]

    time = "started_at" if result == "pending" else "finished_at"

    if result in ['passed', 'fixed']:
        avatar = "https://travis-ci.com/images/logos/TravisCI-Mascot-blue.png"
    elif result in ['pending', 'canceled']:
        avatar = "https://travis-ci.com/images/logos/TravisCI-Mascot-grey.png"
    else:
        avatar = "https://travis-ci.com/images/logos/TravisCI-Mascot-red.png"

    payload = {
        "username": "Travis CI",
        "avatar_url": "https://travis-ci.com/images/logos/TravisCI-Mascot-1.png",
        "embeds": [{
            "color": color,
            "author": {
                "name": PAYLOAD_TITLE.format(**data),
                "url": data["build_url"],
                "icon_url": avatar
            },
            "title": data["message"].splitlines()[0],
            "url": "https://github.com/{repository[owner_name]}/{repository[name]}/pull/{pull_request_number}".format(**data) if data["pull_request"] else "",
            "description": "\n".join(data["message"].splitlines()[1:]),
            "fields": [
            {
                "name": "Commit",
                "value": "[`{commit:.7}`]({compare_url})".format(**data),
                "inline": True,
            },{
                "name": "Branch",
                "value": "[`{branch}`](https://github.com/{repository[owner_name]}/{repository[name]}/tree/{branch})".format(**data),
                "inline": True,
            }
            ],
            "timestamp": data[time]
        }]
    }

    resp = requests.request("POST", DISCORD_WEBHOOK, json=payload, headers={"Content-Type": "application/json"})

    # https://stackoverflow.com/a/19569090
    return resp.text, resp.status_code, resp.headers.items()


@app.errorhandler(500)
def server_error(e):
    logging.exception("Error :/")
    return """
    Idk, server error :/

    <pre>{}</pre>

    sorry
    """.format(e), 500


if __name__ == "__main__":
    app.run(debug=True)
