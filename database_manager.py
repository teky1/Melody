import gspread

gc = gspread.service_account(filename='google_service_account.json')
db = gc.open("MusicBackendDatabase")
playlists = db.worksheet("Playlists")

def createPlaylist(name, author_id, tracks):
    playlists.append_row([name.lower(), str(author_id), ",".join(tracks)])

def getPlaylist(name):
    existing_playlists = playlists.col_values(1)[1:]
    for i,pl in enumerate(existing_playlists):
        if pl == name.lower():
            return playlists.row_values(i+2)
    return None