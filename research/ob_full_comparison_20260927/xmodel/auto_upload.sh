#!/bin/bash
# Auto-upload at experiment end: eval -> git push (small artifacts) ->
# full-evidence tarball parts -> GitHub Release assets via REST API.
# PAT is read from /data/lab/misvis-credentials/PAT, never echoed, never committed.
set -uo pipefail
XM=$1                      # xmodel dir inside the git clone
TAG=${2:-xmodel-20260928-v1}
PAT_FILE=/data/lab/misvis-credentials/PAT
REPO=leolys/naacl
[ -f "$PAT_FILE" ] || { echo "missing PAT file"; exit 1; }
PAT=$(cat "$PAT_FILE")
LOG="$XM/upload_log_$(date -u +%Y%m%dT%H%M%SZ).log"
exec > >(tee -a "$LOG") 2>&1

echo "== auto_upload start $(date -u +%FT%TZ) =="

# 1) scoring (idempotent: output dir removed first)
cd "$XM"
rm -rf eval
python3 eval_xmodel.py --out runs_xmodel/* --output eval || { echo "EVAL FAILED"; exit 1; }

# 2) git push small artifacts (code, summaries, ledgers, eval; no request bodies)
cd "$XM/../.."   # repo root
git add -A research/ob_full_comparison_20260927/xmodel
git commit -m "xmodel run artifacts: cross-model static panel results and eval ($(date -u +%FT%TZ))" || echo "nothing to commit"
git push origin main || { echo "PUSH FAILED"; exit 1; }
echo "== git pushed =="

# 3) evidence tarball: full stage folders (request/response/accepted/failure/identity)
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
TARROOT=/data/lab/evidence_xmodel
mkdir -p "$TARROOT" && cd "$TARROOT" && rm -f xmodel_evidence_${STAMP}* 
tar -czf xmodel_evidence_${STAMP}.tar.gz -C "$XM" runs_xmodel runtime_identity_xmodel.json 2>/dev/null || tar -czf xmodel_evidence_${STAMP}.tar.gz -C "$XM" runs_xmodel
split -b 1900m -d xmodel_evidence_${STAMP}.tar.gz xmodel_evidence_${STAMP}.part-
rm -f xmodel_evidence_${STAMP}.tar.gz
ls -la xmodel_evidence_${STAMP}.part-* | tee "$XM/evidence_parts_${STAMP}.txt"
sha256sum xmodel_evidence_${STAMP}.part-* > "$XM/evidence_parts_${STAMP}.sha256"

# 4) release via REST
AUTH="Authorization: token $PAT"
CREATE=$(curl -s -X POST -H "$AUTH" -H "Accept: application/vnd.github+json" \
  https://api.github.com/repos/$REPO/releases \
  -d "{\"tag_name\":\"$TAG\",\"target_commitish\":\"main\",\"name\":\"xmodel evidence $STAMP\",\"body\":\"Cross-model static panel evidence (xmodel_20260928). Parts are split tar.gz; sha256 in evidence_parts_${STAMP}.sha256. See research/ob_full_comparison_20260927/xmodel/.\"}")
RELID=$(printf '%s' "$CREATE" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('id',''))" 2>/dev/null)
if [ -z "$RELID" ]; then printf '%s' "$CREATE" | head -c 400; echo; echo "RELEASE CREATE FAILED"; exit 1; fi
echo "release id=$RELID tag=$TAG"

upload_asset() { # file, name
  local f=$1 n=$2 ok=0 try
  for try in 1 2 3; do
    code=$(curl -s -o /tmp/asset_resp.json -w '%{http_code}' \
      -X POST -H "$AUTH" -H "Content-Type: application/octet-stream" \
      "https://uploads.github.com/repos/$REPO/releases/$RELID/assets?name=$n" --data-binary @"$f")
    if [ "$code" = "201" ]; then ok=1; echo "asset $n uploaded"; break; fi
    echo "asset $n try $try -> $code $(head -c 200 /tmp/asset_resp.json)"; sleep 20
  done
  [ $ok = 1 ] || return 1
}
FAIL=0
upload_asset "$XM/evidence_parts_${STAMP}.sha256" "evidence_parts_${STAMP}.sha256.txt" || FAIL=1
for f in xmodel_evidence_${STAMP}.part-*; do
  upload_asset "$TARROOT/$f" "$f" || FAIL=1
done
[ $FAIL = 0 ] || { echo "ASSET UPLOAD FAILED"; exit 1; }

# 5) record manifest of what was released, commit it too
python3 - "$XM" "$STAMP" "$TAG" <<'EOF'
import json, hashlib, sys
from pathlib import Path
xm, st, tag = sys.argv[1], sys.argv[2], sys.argv[3]
root = Path(xm)
parts = sorted(root.glob('evidence_parts_%s.sha256' % st))
lines = parts[0].read_text().splitlines() if parts else []
manifest = {'tag': tag, 'created_utc': st,
            'assets': [{'name': l.split()[1], 'sha256': l.split()[0]} for l in lines],
            'upload_log': sorted(p.name for p in root.glob('upload_log_*.log'))[-1]}
(root / 'RESULT_UPLOAD_MANIFEST.json').write_text(json.dumps(manifest, indent=2))
EOF
git add -A research/ob_full_comparison_20260927/xmodel
git commit -m "xmodel evidence release $TAG (manifest + upload log)" || true
git push origin main || true
echo "== auto_upload done $(date -u +%FT%TZ) =="
