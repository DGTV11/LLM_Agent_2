from datetime import datetime
from multiprocessing.connection import Connection
from typing import Any, Dict, List, Literal, Optional

import requests
from bs4 import BeautifulSoup
from pocketflow import *
from pydantic import BaseModel, Field

from function_node import FunctionNode
from memory import FunctionResultContent, Memory, Message


# *duckduckgo_instant_answer
class DuckDuckGoInstantAnswerValidator(BaseModel):
    """Requests an AI-generated abstract and relevant search results from the DuckDuckGo Instant Answer API. To be used when searching for or double-checking factual information when you determine that your internal world model may not be most reliable."""

    query: str = Field(description="Search query.")

    model_config = {"title": "duckduckgo_instant_answer"}


class DuckDuckGoInstantAnswer(FunctionNode):
    name = "duckduckgo_instant_answer"
    validator = DuckDuckGoInstantAnswerValidator

    def exec_function(
        self,
        memory: Memory,
        conn: Connection,
        arguments_validated: DuckDuckGoInstantAnswerValidator,
    ) -> Message:

        url = "https://api.duckduckgo.com/"
        params = {"q": arguments_validated.query, "format": "json"}

        response = requests.get(url, params=params)
        results = response.json()
        abstract_text = results.get("AbstractText")
        abstract_url = results.get("AbstractURL")
        related_topics = list(
            filter(lambda o: not o.get("Name"), results.get("RelatedTopics"))
        )

        return Message(
            message_type="function_res",
            timestamp=datetime.now(),
            content=FunctionResultContent(
                success=True,
                result="\n\n".join(
                    [
                        f"Abstract Text: {abstract_text}",
                        f"Abstract URL: {abstract_url}",
                        f"Related Topics: {related_topics}",
                    ]
                ),
            ),
        )


# *scrape_webpage
class ScrapeWebpageValidator(BaseModel):
    """Scrapes the requested URL using BeautifulSoup."""

    url: str = Field(description="URL to be scraped from.")

    model_config = {"title": "scrape_webpage"}


class ScrapeWebpage(FunctionNode):
    name = "scrape_webpage"
    validator = ScrapeWebpageValidator

    def exec_function(
        self,
        memory: Memory,
        conn: Connection,
        arguments_validated: ScrapeWebpageValidator,
    ) -> Message:
        r = requests.get(url)
        soup = BeautifulSoup(r.content, "html.parser")

        return Message(
            message_type="function_res",
            timestamp=datetime.now(),
            content=FunctionResultContent(
                success=True,
                result="\n\n".join([str(r), "\n", soup.prettify()]),
            ),
        )


FUNCTION_NODES = [DuckDuckGoInstantAnswer(), ScrapeWebpage()]
