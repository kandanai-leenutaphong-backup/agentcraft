from urllib.parse import urlsplit

from azdata import HttpResponse


def cosmos_metadata(request):
    path = urlsplit(request.url).path.rstrip("/")
    if request.method != "GET":
        return None
    if not path:
        return HttpResponse(200, {"id": "fixture-account", "consistencyPolicy": {"defaultConsistencyLevel": "Session"},
                                  "readableLocations": [], "writableLocations": []})
    if path.endswith("/colls/items"):
        return HttpResponse(200, {"id": "items", "_rid": "fixture-container", "partitionKey": {"paths": ["/site"], "kind": "Hash", "version": 2}})
    return None