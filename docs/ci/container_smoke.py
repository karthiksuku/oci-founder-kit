"""Read-only checks against the synthetic ordinary container on loopback."""
import json
import sys
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


def main():
    origin = sys.argv[1]
    url = urlsplit(origin)
    if url.scheme != 'http' or url.hostname != '127.0.0.1' or url.path or url.query or url.fragment or url.username:
        raise SystemExit('The synthetic smoke test requires a loopback HTTP origin.')
    client = build_opener(ProxyHandler({}), NoRedirect())
    def get(path):
        try:
            response = client.open(Request(origin + path), timeout=5)
        except HTTPError as error:
            response = error
        with response:
            return response.status, dict(response.headers), response.read(8192)
    status, headers, body = get('/api/items?category=work')
    assert status == 200 and [row['id'] for row in json.loads(body)['items']] == ['notebook']
    assert headers['Cache-Control'] == 'no-store'
    status, headers, body = get('/start')
    assert status == 307 and headers['Location'] == '/catalogue'
    assert get('/private')[0] == 401
    assert get('/api/items?category=unknown')[0] == 400
    assert b'event: complete' in get('/stream')[2]
    print('Synthetic container filtering, redirect, denial and stream checks passed; OCI not tested.')


if __name__ == '__main__':
    main()
