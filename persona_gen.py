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
        prompt = PERSONA_GEN_PROMPT.format(goals, PERSONA_MAX_WORDS)
        
        res = call_llm()
        pass