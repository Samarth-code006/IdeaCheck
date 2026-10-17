"""Ollama local chat provider. Requests remain on localhost."""
import json
import os
from urllib.request import Request,urlopen


class OllamaLLM:
    name="ollama"
    def __init__(self,model:str|None=None,base_url:str="http://127.0.0.1:11434",timeout:int=120):
        self.model=model or os.getenv("OLLAMA_MODEL","")
        if not self.model: raise ValueError("Set OLLAMA_MODEL before selecting Ollama.")
        self.base_url=base_url.rstrip("/")
        self.timeout=timeout

    def generate_text(self,*,system:str,user:str,prompt_id:str,prompt_version:str,temperature:float=0.0,max_tokens:int=800)->str:
        body={"model":self.model,"stream":False,"messages":[{"role":"system","content":system},{"role":"user","content":user}],"options":{"temperature":temperature,"num_predict":max_tokens}}
        req=Request(self.base_url+"/api/chat",data=json.dumps(body).encode(),headers={"Content-Type":"application/json"},method="POST")
        with urlopen(req,timeout=self.timeout) as response: payload=json.loads(response.read())
        return payload["message"]["content"]

    def generate_json(self,*,system:str,user:str,schema:dict,prompt_id:str,prompt_version:str,temperature:float=0.0,max_tokens:int=1500)->dict:
        body={"model":self.model,"stream":False,"format":schema,"messages":[{"role":"system","content":system},{"role":"user","content":user}],"options":{"temperature":temperature,"num_predict":max_tokens}}
        req=Request(self.base_url+"/api/chat",data=json.dumps(body).encode(),headers={"Content-Type":"application/json"},method="POST")
        with urlopen(req,timeout=self.timeout) as response: payload=json.loads(response.read())
        return json.loads(payload["message"]["content"])
