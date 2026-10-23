"""Cross-check actual good/bad rendered fixtures with Token Plan's VLM tool."""
import base64
import json
from pathlib import Path
import sys
from meme_generator.features.minimax_authoring import MiniMax


def main():
    client=MiniMax(limit=2);report=[]
    try:
        for filename in sys.argv[2:]:
            path=Path(filename)
            result=client._post('/v1/coding_plan/vlm',{'prompt':'Inspect these five diagnostic columns: original source, opaque face replacement, empty captions, new captions, transparent cutout replacement. Ignore the authoring model scores: judge PIXELS ONLY. Does every rendered column completely erase the original eyes, pupils and mouth inside the replaced face, preserve hair/props, and completely erase editable old captions in the empty/new columns? Partial portrait overlays leaving the original mouth or eyes visible are FAILURES. Face-only templates need no caption edits. Return JSON {"passed":true/false,"old_face_fully_removed":true/false,"caption_complete":true/false,"props_preserved":true/false,"reason":"specific pixel evidence"}. Source original itself is the reference, not a replacement output.','image_url':'data:image/jpeg;base64,'+base64.b64encode(path.read_bytes()).decode()})
            report.append({'fixture':str(path),'review':result.get('content','')})
        Path(sys.argv[1]).write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(report,ensure_ascii=False))
    finally:client.close()


if __name__=='__main__':main()
