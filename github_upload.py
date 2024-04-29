from argparse import ArgumentParser
from bisect import insort
from dataclasses import dataclass, replace
from json import loads, dump, load
from html.parser import HTMLParser
from typing import Any, Callable, Dict, List, Tuple, TypeVar
from aiohttp import ClientSession
from asyncio import run, gather, sleep
from os import listdir
from os.path import isfile, join
from re import findall, sub
from shutil import move

# constants
POST_LINK_ID = "f4706281-cc60-4ff0-a0b6-b803683cc24b"

async def main(github_issue_number: int, github_token: str) -> None:
    links = {}
    for idx, filename in enumerate(sorted(listdir("./discourse-export"))):
        if isfile(join("./discourse-export", filename)):
            id, rest = filename.split("_")
            slug, _ = rest.split(".")
            with open(f"./discourse-export/{id}_{slug}.json", "r") as file:
                links[slug] = {"id": id, "idx": idx, "dests": set([slug[:-1] for slug in findall(f'{POST_LINK_ID}/(.*?)"', file.read())])}
    for slug, data in links.items():
        for dest in data["dests"]:
            dest_data = links.get(dest, None)
            if dest_data is None:
                print(f"broken link: {slug}->{dest} (https://github.com/iris-garden/test-process/issues/{github_issue_number + data['idx']})")
            else:
                with open(f"./discourse-export/{data['id']}_{slug}.json", "r") as file:
                    json = sub(f'{POST_LINK_ID}/(.*?)"', f"https://github.com/iris-garden/test-process/issues/{github_issue_number + dest_data['idx']}\\\"", file.read())
                with open(f"./discourse-export/{data['id']}_{slug}.json", "w") as file:
                    file.write(json)
    async with ClientSession() as session:
        count = 0
        for issue in sorted([{"slug": slug, **data} for slug, data in links.items()], key=lambda x: x["idx"]):
            with open(f"./discourse-export/{issue['id']}_{issue['slug']}.json", "r") as file:
                topic = load(file)
            await gather(create_issue(topic, session, github_token))
            move(f"./discourse-export/{issue['id']}_{issue['slug']}.json", f"./uploaded/{issue['id']}_{issue['slug']}.json")
            if count < 19:
                count += 1
            else:
                count = 0
                await sleep(65)

async def create_issue(
    topic: Dict[str, Any], session: ClientSession, github_token: str
) -> str:
    async with session.post(
        "https://api.github.com/repos/iris-garden/test-process/issues",
        json={"title": topic["title"], "body": topic["html"], "labels": ["discourse-old"]},
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {github_token}",
            "Content-Type": "application/json; charset=utf-8",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    ) as response:
        response_json = loads(await response.read())
        if response_json.get("message", None) is not None:
            print(response_json["message"])
            exit(1)

if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("--github_issue_number")
    parser.add_argument("--github_token")
    args = parser.parse_args()
    run(main(int(args.github_issue_number), args.github_token))
