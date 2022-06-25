import json
import base64
import time

import gspread
import requests

gc = gspread.service_account(filename='google_service_account.json')
db = gc.open("MusicBackendDatabase")
playlists = db.worksheet("Playlists")
auth_db = db.worksheet("SpotifyAuth")

with open("secrets.json") as f:
    secrets = json.load(f)

def createPlaylist(name, author_id, tracks):
    playlists.append_row([name.lower(), str(author_id), ",".join(tracks)])

def getPlaylist(name):
    existing_playlists = playlists.col_values(1)[1:]
    for i,pl in enumerate(existing_playlists):
        if pl == name.lower():
            return playlists.row_values(i+2)
    return None

def getSpotifyKey(id):
    local = auth_db.get_values("A2:D1000")
    for entry in local:
        if entry[0] == str(id):
            if int(entry[3]) > time.time():
                return refreshSpotifyToken(entry, local)
            else:
                return entry
    return None

def refreshSpotifyToken(entry, local=None):

    token_url = 'https://accounts.spotify.com/api/token'
    authorization = secrets["spotify_client_id"] + ":" + secrets["spotify_client_secret"]
    authorization = base64.b64encode(authorization.encode("ascii")).decode("ascii")

    headers = {'Authorization': "Basic " + authorization,
               'Accept': 'application/json',
               'Content-Type': 'application/x-www-form-urlencoded'}

    body = {'refresh_token': entry[2], 'grant_type': 'refresh_token'}

    post_response = requests.post(token_url, headers=headers, data=body)

    local = local if local is not None else auth_db.get_values("A2:D1000")
    entry = [
        entry[0],
        post_response.json()["access_token"],
        entry[2],
        int(post_response.json()["expires_in"]) + int(time.time())
    ]
    added = False
    for i, row in enumerate(local):
        if row[0] == entry[0]:
            local[i] = entry
            added = True
            break
    if not added:
        local.append(entry)
    auth_db.update("A2:D1000", local, value_input_option="USER_ENTERED")
    return entry