import json
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
from curate import Round, serve, summary  # noqa: E402


def test_a_round_is_served_and_its_answers_kept(tmp_path):
    r = Round("teste", title="Teste", blind=True, root=tmp_path)
    g = r.group("tons", tasks=["pick", "rate:robótico", "abx:grave|agudo", "marks", "notes"], reference="grave",
                targets={"hz": 220})
    t = np.arange(4410) / 44100
    g.add("grave", 0.5 * np.sin(2 * np.pi * 220 * t), sr=44100, metrics={"hz": 220})
    g.add("agudo", 0.5 * np.sin(2 * np.pi * 440 * t), sr=44100, metrics={"hz": 440})
    r.save()
    server = serve(tmp_path, 0, open_browser=False)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        assert b"<title>Curadoria</title>" in urllib.request.urlopen(base + "/").read()
        assert json.loads(urllib.request.urlopen(base + "/api/rounds").read())[0]["name"] == "teste"
        m = json.loads(urllib.request.urlopen(base + "/api/round/teste").read())["manifest"]
        g0 = m["groups"][0]
        seg = g0["segments"]
        assert g0["reference"] == seg[0]["id"] and g0["tasks"][2]["x"] in (seg[0]["id"], seg[1]["id"])
        assert urllib.request.urlopen(f"{base}/files/teste/{seg[1]['file']}").read()[:4] == b"RIFF"
        answers = {"g1": {"pick": seg[1]["id"], "rate:robótico": {seg[0]["id"]: 2}, "notes": "ok",
                          "marks": [{"seg": seg[0]["id"], "t": 0.05, "note": "aqui"}]}}
        req = urllib.request.Request(f"{base}/api/round/teste/answers", json.dumps(answers).encode(), method="POST")
        assert json.loads(urllib.request.urlopen(req).read())["ok"]
        assert json.loads((tmp_path / "teste" / "answers.json").read_text(encoding="utf-8")) == answers
        assert "pick: agudo" in summary("teste", tmp_path) and "grave @ 0.05s aqui" in summary("teste", tmp_path)
        for bad in ("/files/teste/../../secret", "/files/..%2F/teste", "/api/round/..%2Fteste"):
            try:
                urllib.request.urlopen(base + bad)
                raise AssertionError(bad)
            except urllib.error.HTTPError as e:
                assert e.code == 404
    finally:
        server.shutdown()
