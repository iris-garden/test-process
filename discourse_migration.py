from argparse import ArgumentParser
from dataclasses import dataclass
from datetime import datetime, timedelta
from json import dumps, loads
from time import sleep
from typing import Any, Callable, Dict, List, TypeVar
from urllib.request import Request, urlopen


# generic
identity = lambda x: x
frozen_dataclass = dataclass(frozen=True)


# types
CallbackResponse = TypeVar("CallbackResponse")
Callback = Callable[[Dict[str, Any]], CallbackResponse]


@frozen_dataclass
class DiscoursePost:
    id: int
    username: str
    html: str


@frozen_dataclass
class DiscourseTopic:
    id: int
    title: str
    posts: List[DiscoursePost]


# request helpers
def make_request(request: Request, callback: Callback) -> CallbackResponse:
    with urlopen(request) as response:
        output = callback(loads(response.read()))
    return output


def get(url: str, callback: Callback = identity) -> CallbackResponse:
    request = Request(url=url, method="GET")
    return make_request(request, callback)


def post_json(
    url: str,
    data: Dict[str, Any],
    callback: Callback = identity,
    headers: Dict[str, str] = {}
) -> CallbackResponse:
    request = Request(
        url=url,
        method="POST",
        headers={
            **{'Content-Type': 'application/json; charset=utf-8'},
            **headers
        },
        data=dumps(data).encode()
    )
    return make_request(request, callback)


# discourse api helpers
def get_discourse_topics(last_page: int) -> List[DiscourseTopic]:
    page = 0
    topics = []
    while page <= last_page:
        topics = [
            *topics,
            *get(
                f"https://discuss.hail.is/latest.json?page={page}",
                parse_topics
            )
        ]
        page = page + 1
    return topics


def parse_topics(response: Dict[str, Any]) -> List[DiscourseTopic]:
    return [
        DiscourseTopic(
            topic["id"],
            topic["title"],
            get_topic_posts(topic["id"])
        )
        for topic in response["topic_list"]["topics"]
        if (
            datetime.now() - datetime.strptime(
                topic["last_posted_at"].partition(".")[0],
                "%Y-%m-%dT%H:%M:%S"
            )
        ) <= timedelta(days=31)
    ]


def get_topic_posts(topic_id: int) -> List[DiscoursePost]:
    return get(f"https://discuss.hail.is/t/{topic_id}.json", get_posts)


def get_posts(topic: Dict[str, Any]) -> List[DiscoursePost]:
    return [
        get(f"https://discuss.hail.is/posts/{post['id']}.json", parse_post)
        for post in topic["post_stream"]["posts"]
    ]


def parse_post(post: Dict[str, Any]) -> DiscoursePost:
    return DiscoursePost(post["id"], post["username"], post["cooked"])


def to_issue_body(topic: DiscourseTopic) -> str:
    return "\n\n".join([
        f"<h2><a href='{post_url(topic.id, index)}'>{post.username} said</a>:</h2>\n{post.html}"
        for index, post in enumerate(topic.posts)
    ])


def post_url(topic_id: str, post_index: int) -> str:
    return f"{topic_url(topic_id)}/{post_index + 1}"


def topic_url(topic_id: str) -> str:
    return f"https://discuss.hail.is/t/{topic_id}"


# github api helpers
def create_issue(token: str, topic: DiscourseTopic) -> None:
    post_json(
        "https://api.github.com/repos/iris-garden/test-process/issues",
        {
            "title": topic.title,
            "body": to_issue_body(topic),
            "labels": ["discourse"]
        },
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28"
        }
    )


# main script
def main(last_discourse_page: int, github_token: str) -> None:
    for topic in get_discourse_topics(last_discourse_page):
        create_issue(github_token, topic)
        # don't wanna get rate-limited
        sleep(1)


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument('--github-token')
    args = parser.parse_args()
    LAST_DISCOURSE_PAGE = 56
    main(LAST_DISCOURSE_PAGE, args.github_token)
