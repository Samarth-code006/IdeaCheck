"""Generic OpenAI-compatible chat completions client using only the stdlib."""
import json
import os
import random
import re
import time
import threading
from urllib.request import Request, urlopen
from urllib.error import HTTPError,URLError
from app.providers.ratelimit import TokenBucket
from app.config import get_config


class OpenAICompatibleLLM:
    name="openai_compat"
    def __init__(self,base_url:str,model:str,api_key:str|None=None,rpm:int=15,timeout:int=30):
        if not base_url or not model:
            raise ValueError("Set LLM_BASE_URL and LLM_MODEL before selecting openai_compat.")
        self.base_url=base_url.rstrip("/")
        self.model=model
        self.api_key=api_key or os.getenv("LLM_API_KEY","")
        self.timeout=timeout
        self.bucket=TokenBucket(rpm)
        settings=get_config()["providers"]
        self.max_retries=settings["llm_max_retries"]
        self.max_backoff=settings["llm_retry_backoff_seconds"]
        self.semaphore=threading.BoundedSemaphore(settings["llm_max_concurrency"])

    def generate_text(self,*,system:str,user:str,prompt_id:str,prompt_version:str,temperature:float=0.0,max_tokens:int=800)->str:
        with self.semaphore:
            for attempt in range(self.max_retries):
                self.bucket.acquire()
                body={"model":self.model,"messages":[{"role":"system","content":system},{"role":"user","content":user}],"temperature":temperature,"max_tokens":max_tokens}
                headers={"Content-Type":"application/json"}
                if self.api_key: headers["Authorization"]="Bearer "+self.api_key
                req=Request(self.base_url+"/chat/completions",data=json.dumps(body).encode(),headers=headers,method="POST")
                try:
                    with urlopen(req,timeout=self.timeout) as response:
                        payload=json.loads(response.read())
                    return payload["choices"][0]["message"]["content"]
                except HTTPError as exc:
                    if attempt+1>=self.max_retries or exc.code not in {408,429,500,502,503,504}: raise
                    retry_after=exc.headers.get("Retry-After") if exc.headers else None
                    wait=float(retry_after) if retry_after else min(2**attempt+random.random(),self.max_backoff)
                    time.sleep(max(0,min(wait,self.max_backoff)))
                except (URLError,TimeoutError):
                    if attempt+1>=self.max_retries: raise
                    time.sleep(min(2**attempt+random.random(),self.max_backoff))
        raise RuntimeError("LLM provider exhausted its retry budget.")

    def generate_json(self,*,system:str,user:str,schema:dict,prompt_id:str,prompt_version:str,temperature:float=0.0,max_tokens:int=1500)->dict:
        reminder="Return only JSON matching this schema:\n"+json.dumps(schema,ensure_ascii=False)
        raw=self.generate_text(system=system+"\n"+reminder,user=user,prompt_id=prompt_id,prompt_version=prompt_version,temperature=temperature,max_tokens=max_tokens)
        raw=re.sub(r"^```(?:json)?\s*|\s*```$","",raw.strip(),flags=re.I)
        start=raw.find("{")
        return json.loads(raw[start:] if start>=0 else raw)
