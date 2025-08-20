from pocketflow import *
import yaml
from prompts import PERSONA_GEN_PROMPT

class GeneratePersona(Node):
    def prep(self, shared):
        goals = shared['goals']
        return goals
        
    def exec(self, goals):
        pass