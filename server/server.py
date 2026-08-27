from http.server import BaseHTTPRequestHandler,HTTPServer
import json,urllib.request,urllib.error,os,re
MODEL=os.getenv("PROMPT_SAVER_MODEL","qwen2.5:3b"); OLLAMA="http://127.0.0.1:11434/api/generate"
SYSTEM="""You are PromptSaver. Rewrite the user's messy prompt into the shortest clear prompt that preserves full intent.
Preserve every requirement, constraint, negation (NOT/DO NOT/NEVER/ONLY/WITHOUT), number, URL, filename, identifier, technical term, code block, error message and output format.
Remove filler, repetition and unnecessary conversational wording. Reorganize scattered requirements when useful. Do not invent requirements.
If already concise, keep it essentially unchanged. Code blocks must be copied exactly. Return ONLY the optimized prompt."""
def est(s): return max(0,(len(s.strip())+3)//4)
def valid(a,b):
    checks=[]
    for x in re.findall(r'```[\s\S]*?```|https?://\S+|\b\d+(?:\.\d+)?%?\b',a): checks.append(x in b)
    for x in ["do not","don't","never","only","without","must not"]:
        if re.search(r"\b"+re.escape(x)+r"\b",a,re.I): checks.append(bool(re.search(r"\b"+re.escape(x)+r"\b",b,re.I)))
    return all(checks) if checks else True
def generate(prompt):
    body=json.dumps({"model":MODEL,"system":SYSTEM,"prompt":prompt,"stream":False,"options":{"temperature":0.1,"top_p":0.9}}).encode()
    req=urllib.request.Request(OLLAMA,data=body,headers={"Content-Type":"application/json"},method="POST")
    with urllib.request.urlopen(req,timeout=180) as r:return json.loads(r.read())["response"].strip()
class H(BaseHTTPRequestHandler):
    def out(self,status,data):
        b=json.dumps(data).encode();self.send_response(status);self.send_header("Content-Type","application/json");self.send_header("Access-Control-Allow-Origin","*");self.send_header("Access-Control-Allow-Headers","Content-Type, X-Requested-With");self.send_header("Access-Control-Allow-Methods","GET,POST,OPTIONS");self.send_header("Access-Control-Allow-Private-Network","true");self.end_headers();self.wfile.write(b)
    def do_OPTIONS(self):self.out(200,{"ok":True})
    def do_GET(self):
        if self.path!="/health":return self.out(404,{"detail":"Not found"})
        try:
            with urllib.request.urlopen("http://127.0.0.1:11434/api/tags",timeout=3) as r:d=json.load(r)
            names=[m.get("name","") for m in d.get("models",[])]
            ok=any(n==MODEL or n.startswith(MODEL+":") for n in names)
            self.out(200,{"ok":ok,"model":MODEL,"message":"" if ok else f"Run: ollama pull {MODEL}"})
        except Exception:self.out(503,{"ok":False,"model":MODEL,"message":"Ollama is not running"})
    def do_POST(self):
        if self.path!="/optimize":return self.out(404,{"detail":"Not found"})
        try:
            n=int(self.headers.get("Content-Length","0"));p=json.loads(self.rfile.read(n)).get("prompt","").strip()
            if not p:return self.out(400,{"detail":"Prompt is empty"})
            if len(p)>30000:return self.out(413,{"detail":"Prompt exceeds 30,000 characters"})
            o=generate(p)
            if not o:raise RuntimeError("Local model returned an empty response")
            if est(o)>est(p):o=p
            self.out(200,{"optimized":o,"original_tokens":est(p),"optimized_tokens":est(o),"model":MODEL,"validation_passed":valid(p,o)})
        except urllib.error.URLError:self.out(503,{"detail":f"Cannot reach Ollama. Start Ollama and install {MODEL}."})
        except Exception as e:self.out(500,{"detail":str(e)})
if __name__=="__main__":print(f"PromptSaver server on http://127.0.0.1:8765 using {MODEL}");HTTPServer(("127.0.0.1",8765),H).serve_forever()
