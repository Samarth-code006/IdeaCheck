"""Schema-validated extraction with bounded repair retries and heuristic fallback."""
import json
import logging
import time
from pydantic import ValidationError
from app.contracts import ProposalProfile
from app.extraction.heuristic import extract_profile as heuristic_profile
from app.prompts.extract_proposal import SYSTEM, VERSION
from app.providers.cache import cached_generate_json
from app.providers.factory import get_llm_provider

logger=logging.getLogger(__name__)


class ExtractionResult:
    def __init__(self,profile:ProposalProfile,source:str,warnings:list[str]):
        self.profile=profile
        self.source=source
        self.warnings=warnings


def extract_proposal(text:str,provider=None)->ExtractionResult:
    provider=provider or get_llm_provider()
    schema=ProposalProfile.model_json_schema()
    errors=[]
    for attempt in range(3):
        prompt= text if not errors else text+"\n\nYour previous JSON failed validation: "+errors[-1]+". Return corrected JSON matching the schema exactly."
        started=time.monotonic()
        try:
            result=cached_generate_json(provider,system=SYSTEM,user=prompt,schema=schema,
                                        prompt_id="proposal.extract",prompt_version=VERSION,temperature=0)
            if result is None:
                return ExtractionResult(heuristic_profile(text),"heuristic",["Profile was not cached in read-only demo mode."])
            profile=ProposalProfile.model_validate(result)
            logger.info("profile extraction prompt_id=proposal.extract attempt=%s latency_ms=%s cache_mode=enabled",attempt+1,int((time.monotonic()-started)*1000))
            return ExtractionResult(profile,"llm" if provider.name!="fake" else "heuristic",[] if provider.name!="fake" else ["Deterministic fake provider delegates to the heuristic extractor."])
        except (ValidationError,ValueError,json.JSONDecodeError,KeyError) as exc:
            errors.append(str(exc))
        except Exception as exc:
            errors.append(str(exc))
            break
    return ExtractionResult(heuristic_profile(text),"heuristic",["LLM extraction failed validation or provider access; rule-based profile used."])
