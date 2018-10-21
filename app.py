import base64
import json
import logging

from flask import Flask, request, abort
from OpenSSL.crypto import verify, load_publickey, FILETYPE_PEM, X509
from OpenSSL.crypto import Error as SignatureError
import requests
import yaml


PAYLOAD_TITLE = "Build #{number} {status_message} - {repository[owner_name]}/{repository[name]}"
PAYLOAD_COMMIT_URL = "https://github.com/{repository[owner_name]}/{repository[name]}/commit/{commit}"


with open("config.yaml") as file:
    config = yaml.load(file)

DISCORD_WEBHOOK = config["discord_webhook"]
AUTHORIZED_OWNERS = config["authorized_owners"]
TRAVIS_CONFIG_URL = "https://api.travis-ci.org/config"
COLORS = config["colors"]


app = Flask(__name__)

@app.route("/notify", methods=["POST"])
def webhook():
    raw_data = request.form["payload"]
    signature = base64.b64decode(request.headers.get("Signature"))
    data = json.loads(raw_data)

    if data["repository"]["owner_name"] not in AUTHORIZED_OWNERS:
        abort(401)

    try:
        check_authorized(signature, PUBLIC_KEY, raw_data)
    except SignatureError:
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

# https://gist.github.com/andrewgross/8ba32af80ecccb894b82774782e7dcd4
def get_travis_public_key():
    """
    Returns the PEM encoded public key from the Travis CI /config endpoint
    """
    response = requests.get(TRAVIS_CONFIG_URL, timeout=10.0)
    response.raise_for_status()
    return response.json()['config']['notifications']['webhook']['public_key']

def check_authorized(signature, public_key, payload):
    """
    Convert the PEM encoded public key to a format palatable for pyOpenSSL,
    then verify the signature
    """
    pkey_public_key = load_publickey(FILETYPE_PEM, public_key)
    certificate = X509()
    certificate.set_pubkey(pkey_public_key)
    verify(certificate, signature, payload, str('sha1'))

PUBLIC_KEY = get_travis_public_key()

if __name__ == "__main__":
    app.run(debug=True)
