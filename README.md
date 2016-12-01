# omnifocus-to-kanban

## What is this?

This is a tool that synchronises data from [OmniFocus](http://www.omnigroup.com/omnifocus) with a [LeanKit](https://leankit.com) or [Trello](https://trello.com) board.

## Why?

This allows you to visualise your Omnifocus data on a Kanban board or task board. I prefer this to manage my work in progress than using Omnifocus alone. Here's a [blog I wrote](http://rhydlewis.net/blog/2015/9/29/how-i-use-personal-kanban-to-stay-in-control-of-my-work-and-get-stuff-done-part-2) with more info on my thinking.

## How to install

### Dependencies

This tool needs these libraries to function correctly:

* requests (2.11.1)
* trello (0.9.1)
* docopt (0.6.2)
* sqlalchemy 

Run:

`python setup.py install`

to install them.

## How to use

### LeanKit

#### Configuration

Copy the `leankit-config.yaml.example` file as `leankit-config.yaml`. Edit the file as follows:

    email: your Leankit email address
    password: your Leankit password
    account: your Leankit account name
    board_id: your board ID
    completed_lanes:
      - list of Leankit lane ID's that indicate which lanes contain completed work

If you don't know the lane ID's for your board, use:

`./bin/leankit-lanes`

#### Running

`./bin/of-to-kb --leankit`

### Trello

#### Configuration

TODO

#### Running

`./bin/of-to-kb --trello`


## Thanks

* The Lp2Kanban team who provided the bulk of the code for interacting with the LeanKit API via Python https://code.launchpad.net/lp2kanban

