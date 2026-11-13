"""AU Classical Piano Uploader - complete upload script.

Uploads one of the owner's own finished videos to the owner's own channel, sets its thumbnail,
adds it to a playlist and reads the result back to confirm it published correctly.

Usage:
    python upload.py --token token.json --video video.mp4 --meta meta.json [--thumb thumb.jpg] [--playlist PLAYLIST_ID]

meta.json: {"title": "...", "description": "...", "tags": [...], "categoryId": "10",
            "privacyStatus": "public", "containsSyntheticMedia": false}
token.json: OAuth 2.0 authorized-user file (client_id, client_secret, refresh_token) created when the
owner signs in with Google. Tokens are kept on the owner's computer only.
"""
import argparse, json, os, sys, time, urllib.error, urllib.parse, urllib.request

API = 'https://www.googleapis.com/youtube/v3'
UPLOAD = 'https://www.googleapis.com/upload/youtube/v3'
CHUNK = 16 * 1024 * 1024


def access_token(path):
    t = json.load(open(path, encoding='utf-8'))
    data = urllib.parse.urlencode({'client_id': t['client_id'], 'client_secret': t['client_secret'],
                                   'refresh_token': t['refresh_token'], 'grant_type': 'refresh_token'}).encode()
    with urllib.request.urlopen('https://oauth2.googleapis.com/token', data, timeout=60) as r:
        return json.load(r)['access_token']


def call(tok, method, url, body=None, headers=None, raw=None):
    h = {'Authorization': 'Bearer ' + tok}
    h.update(headers or {})
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    if body is not None:
        h.setdefault('Content-Type', 'application/json; charset=utf-8')
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    with urllib.request.urlopen(req, timeout=300) as r:
        txt = r.read()
        return r.status, r.headers, (json.loads(txt) if txt else {})


def upload_video(tok, video, meta):
    body = {'snippet': {'title': meta['title'], 'description': meta.get('description', ''),
                        'tags': meta.get('tags', []), 'categoryId': meta.get('categoryId', '10')},
            'status': {'privacyStatus': meta.get('privacyStatus', 'private'),
                       'selfDeclaredMadeForKids': False,
                       'containsSyntheticMedia': bool(meta.get('containsSyntheticMedia', False))}}
    size = os.path.getsize(video)
    _, hdr, _ = call(tok, 'POST', UPLOAD + '/videos?uploadType=resumable&part=snippet,status', body,
                     {'X-Upload-Content-Type': 'video/*', 'X-Upload-Content-Length': str(size)})
    session = hdr['Location']
    sent = 0
    with open(video, 'rb') as f:
        while sent < size:
            chunk = f.read(CHUNK)
            end = sent + len(chunk) - 1
            for attempt in range(5):
                try:
                    req = urllib.request.Request(session, data=chunk, method='PUT', headers={
                        'Authorization': 'Bearer ' + tok, 'Content-Length': str(len(chunk)),
                        'Content-Range': 'bytes %d-%d/%d' % (sent, end, size)})
                    with urllib.request.urlopen(req, timeout=600) as r:
                        return json.load(r)['id']          # final chunk: 200/201 with the video resource
                except urllib.error.HTTPError as e:
                    if e.code == 308:                       # chunk accepted, continue
                        break
                    if e.code >= 500 and attempt < 4:
                        time.sleep(2 ** attempt); continue
                    raise
            sent = end + 1
            print('uploaded %.1f%%' % (100.0 * sent / size), flush=True)
    raise RuntimeError('upload did not complete')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--token', required=True)
    p.add_argument('--video', required=True)
    p.add_argument('--meta', required=True)
    p.add_argument('--thumb')
    p.add_argument('--playlist')
    a = p.parse_args()
    meta = json.load(open(a.meta, encoding='utf-8'))
    tok = access_token(a.token)

    vid = upload_video(tok, a.video, meta)
    print('video id', vid)
    if a.thumb:
        with open(a.thumb, 'rb') as f:
            call(tok, 'POST', UPLOAD + '/thumbnails/set?videoId=' + vid, raw=f.read(),
                 headers={'Content-Type': 'image/jpeg' if a.thumb.lower().endswith(('.jpg', '.jpeg')) else 'image/png'})
        print('thumbnail set')
    if a.playlist:
        call(tok, 'POST', API + '/playlistItems?part=snippet',
             {'snippet': {'playlistId': a.playlist, 'resourceId': {'kind': 'youtube#video', 'videoId': vid}}})
        print('added to playlist', a.playlist)

    # read back and confirm
    _, _, r = call(tok, 'GET', API + '/videos?part=snippet,status&id=' + vid)
    item = r['items'][0]
    ok = (item['snippet']['title'] == meta['title'] and
          item['status']['privacyStatus'] == meta.get('privacyStatus', 'private'))
    print(json.dumps({'videoId': vid, 'url': 'https://www.youtube.com/watch?v=' + vid,
                      'uploadStatus': item['status'].get('uploadStatus'),
                      'privacyStatus': item['status']['privacyStatus'], 'verified': ok}, indent=1))
    sys.exit(0 if ok else 2)


if __name__ == '__main__':
    main()
