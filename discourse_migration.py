from argparse import ArgumentParser
from dataclasses import dataclass
from datetime import datetime, timedelta
from json import dumps, loads
from html.parser import HTMLParser
from typing import Any, Callable, Dict, List, Tuple, TypeVar
from aiohttp import ClientSession
from asyncio import run, create_task, gather, sleep

# constants
POST_LINK_ID = "f4706281-cc60-4ff0-a0b6-b803683cc24b"

# types
CallbackResponse = TypeVar("CallbackResponse")
Callback = Callable[[Dict[str, Any]], CallbackResponse]


@dataclass(frozen=True)
class DiscoursePost:
    id: int
    topic_id: int
    username: str
    html: str


@dataclass(frozen=True)
class DiscourseTopic:
    id: int
    slug: str
    title: str
    posts: List[DiscoursePost]


# html parser
class DiscourseHTMLParser(HTMLParser):
    def __init__(self: "DiscourseHTMLParser") -> None:
        super().__init__()
        self.output_html = ""
        self.post_links = set()
        # relative file links starting with /
        self.relative_link = False
        # link previews
        self.link_preview = False
        self.link_preview_url = None
        # code blocks
        self.code_block_pre = False
        self.code_block_code = False
        # @ mentions
        self.mention = False

    def _decl_handler(self: "DiscourseHTMLParser", decl: str) -> None:
        self.output_html += f"<!{decl}>"

    def _ref_handler(self: "DiscourseHTMLParser", name: str) -> None:
        self.output_html += f"&{name};"

    def _starttag_handler(suffix: str = "") -> None:
        def inner(
            self: "DiscourseHTMLParser", tag: str, attrs: List[Tuple[str, str]]
        ) -> None:
            attr_dict = dict(attrs)
            if tag == "a":
                link = attr_dict.get("href", "")
                if "mention" in attr_dict.get("class", ""):
                    self.mention = True
                elif link.startswith("/"):
                    self.relative_link = True
                elif "https://discuss.hail.is/t/" in link:
                    slug = link.removeprefix("https://discuss.hail.is/t/").split("/")[0]
                    self.post_links.add(slug)
                    self.output_html += f'<a href="{POST_LINK_ID}/{slug}">'
            elif (
                tag == "aside"
                and "onebox" in attr_dict.get("class", "")
                and "data_onebox_source" in attr_dict
            ):
                self.link_preview_url = attr_dict["data_onebox_source"]
                self.output_html += f'\n<a href="{self.link_preview_url}">'
                self.link_preview = True
            elif tag == "pre":
                self.code_block_pre = True
            elif self.code_block_pre:
                if tag == "code":
                    self.output_html += "\n\n```python\n"
                    self.code_block_code = True
            else:
                attr_str_prefix = " " if len(attrs) > 0 else ""
                attr_str = " ".join([f'{key}="{value}"' for key, value in attrs])
                self.output_html += f"<{tag}{attr_str_prefix}{attr_str}{suffix}>"

        return inner

    handle_charref = _ref_handler
    handle_decl = _decl_handler
    handle_entityref = _ref_handler
    handle_startendtag = _starttag_handler(" /")
    handle_starttag = _starttag_handler()
    unknown_decl = _decl_handler

    def handle_comment(self: "DiscourseHTMLParser", data: str) -> None:
        self.output_html += f"<!--{data}-->"

    def handle_data(self: "DiscourseHTMLParser", data: str) -> None:
        if self.link_preview:
            self.output_html += f"{self.link_preview_url}"
        elif self.mention:
            self.output_html += f'{data.partition("@")[2]}'
        else:
            self.output_html += data

    def handle_endtag(self: "DiscourseHTMLParser", tag: str) -> None:
        if tag == "a":
            if self.mention:
                self.mention = False
            elif self.relative_link:
                self.relative_link = False
        elif tag == "aside" and self.link_preview:
            self.output_html += "</a>\n"
            self.link_preview = False
            self.link_preview_url = None
        elif tag == "pre":
            self.code_block_pre = False
        elif self.code_block_pre:
            if tag == "code":
                self.output_html += "\n```\n\n"
                self.code_block_code = False
        else:
            self.output_html += f"</{tag}>"

    def handle_pi(self: "DiscourseHTMLParser", data: str) -> None:
        self.output_html += f"<?{data}>"

# main script
# TODO go through the topics in order of creation, make a github issue for each one, if it has links check that the link goes to something already created, otherwise make it a dummy link and keep it in a list, and then manually go through at the end and fix the dummy links :shrug:
# or, almost this, but dummy links while parsing, replace before uploading to GH unless not found, then print out list at end of links to edit
# we could go through and detect cycles in the links and do something really clever as far as, if there are no cycles, we can create everything in an order that makes all the links work, but frankly i don't think that's worth the effort unless it turns out we have an absolute ton of links to things that weren't already created at the time of the original topic creation
# TODO once we create the github issue, go back and comment and close the discourse topic
async def main(discourse_page: int, github_token: str) -> None:
    async with ClientSession() as session:
        pages = await run_tasks([parse_page(page, session) for page in range(discourse_page + 1)])
        topics = await run_tasks([parse_topic(topic["id"], session) for page in pages for topic in page["topic_list"]["topics"]])
        posts = await run_tasks([parse_post(post["id"], session) for topic in topics for post in topic["post_stream"]["posts"]])
        topic_acc = {topic["id"]: {"fields": topic, "posts": []} for topic in topics}
        for post in posts:
            topic_acc[post.topic_id]["posts"].append(post)
        topics = [DiscourseTopic(topic["fields"]["id"], topic["fields"]["slug"], topic["fields"]["title"], topic["posts"]) for topic_id, topic in topic_acc.items()]

        links = {}
        for topic in topics:
            topic_html = ""
            links[topic.slug] = set()
            for post in topic.posts:
                parser = DiscourseHTMLParser()
                parser.feed(post.html)
                topic_html += f"<h2>{post.username} said:</h2>\n{parser.output_html}\n\n"
                links[topic.slug] |= parser.post_links

        print(links)


async def run_tasks(tasks):
    result = []
    while len(tasks) != 0:
        if len(tasks) > 5:
            result += await gather(*tasks[:4])
            tasks = tasks[4:]
            await sleep(1/2)
        else:
            result += await gather(*tasks)
            tasks = []
    return result


async def parse_page(discourse_page: int, session) -> None:
    async with session.get(f"https://discuss.hail.is/latest.json?page={discourse_page}") as page_response:
        return await page_response.json()


async def parse_topic(topic_id: int, session) -> None:
    async with session.get(f"https://discuss.hail.is/t/{topic_id}.json") as topic_response:
        return loads(await topic_response.read())


async def parse_post(post_id: int, session) -> None:
    async with session.get(f"https://discuss.hail.is/posts/{post_id}.json") as post_response:
        post_response_json = loads(await post_response.read())
        return DiscoursePost(post_response_json["id"], post_response_json["topic_id"], post_response_json["username"], post_response_json["cooked"])


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("--page")
    parser.add_argument("--github_token")
    args = parser.parse_args()
    run(main(int(args.page), args.github_token))


# issue_url = post_json(
#     "https://api.github.com/repos/iris-garden/test-process/issues",
#     {"title": topic.title, "body": topic_html, "labels": ["discourse-old"]},
#     issue['url'],
#     headers={
#         "Accept": "application/vnd.github+json",
#         "Authorization": f"Bearer {github_token}",
#         "X-GitHub-Api-Version": "2022-11-28",
#     },
# )
# def post_json(
#     url: str,
#     data: Dict[str, Any],
#     callback: Callback = lambda x: x,
#     headers: Dict[str, str] = {},
# ) -> CallbackResponse:
#     return make_request(
#         Request(
#             url=url,
#             method="POST",
#             headers={**{"Content-Type": "application/json; charset=utf-8"}, **headers},
#             data=dumps(data).encode(),
#         ),
#         callback
#     )
# def make_request(request: Request, callback: Callback) -> CallbackResponse:
#     with urlopen(request) as response:
#         output = callback(loads(response.read()))
#     return output
