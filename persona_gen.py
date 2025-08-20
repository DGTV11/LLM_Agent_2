from pocketflow import *
import yaml
from prompts import PERSONA_GEN_PROMPT
from config import PERSONA_MAX_WORDS
from llm import call_llm

class GeneratePersona(Node):
    def prep(self, shared):
        goals = shared['goals']
        
        return goals
        
    def exec(self, goals):
        resp = call_llm({'role': 'user', 'content': PERSONA_GEN_PROMPT.format(goals, PERSONA_MAX_WORDS)})
        
        yaml_str = resp.split("```yaml")[1].split("```")[0].strip()
        result = yaml.safe_load(yaml_str)
        
        assert isinstance(result, dict)
        assert "persona" in result
        assert isinstance(result['persona'], str)
        assert len(result['persona'].split()) <= PERSONA_MAX_WORDS
        
        return result['persona']
        
    def post(self, shared, prep_res, exec_res):
        shared['persona'] = exec_res