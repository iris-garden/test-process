# hail team process updates (proposal)

## zulip

### archive some channels

<img
    width="267"
    alt="Screenshot 2023-08-16 at 12 52 23 copy"
    src="https://github.com/iris-garden/test-process/assets/84595986/ceb3798c-0551-4b84-87b0-bf58b89f6263">

> also can we please make the capitalization consistent?

* `#linalg`, `#test`, `#zulip`
  * no replacement needed
* `#announce`
  * use `#general` instead
* `#workshop`
  * use per-workshop channels like existing `#atgu welcome workshop 2022` instead
* `#cloud support`, `#discussposts`, `#devforumposts`, `#feature requests`,
  `#hail 0.1 support`, `#hail batch support`, `#hail query 0.2 support`
  * use labeled GitHub Issues instead

### open questions
* `#github`: does anyone currently use this instead of normal github notifs?
* `#hail variants`: what is this currently used for?

## discourse (discuss.hail.is)

### migrate to github issues
* use [script](discourse_migration.py) to create a github issue for each
  remaining topic and post a link to it
* create a pinned topic saying that we've migrated
* [disable creation of new topics or posts](https://meta.discourse.org/t/shut-down-the-forum-turn-off-posting/89542/5)
* after a month, shut down the board
