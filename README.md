# omnifocus-to-kanban

## What is this?

This is a tool that synchronises data from [OmniFocus](http://www.omnigroup.com/omnifocus) to a Kanban board (e.g. [KanbanFlow](https://kanbanflow.com/)).

## Why?

This allows you to visualise your Omnifocus actions on a Kanban board. I prefer this to manage my work in progress than using Omnifocus alone. Here's a [blog I wrote](http://rhydlewis.net/blog/2015/9/29/how-i-use-personal-kanban-to-stay-in-control-of-my-work-and-get-stuff-done-part-2) with more info on my thinking.

## How to install

### Dependencies

This tool needs Python 3 and [these libraries](https://github.com/rhydlewis/omnifocus-to-kanban/blob/master/requirements.txt) to run.

Run:

`pip install -r requirements.txt`

to install them.

## How to use

### Kanban Flow

1. Copy the `kanbanflow-config.yaml.example` file as `kanbanflow-config.yaml`. Edit the file to include your API token, lane IDs and contexts.
2. Run `of-to-kb --kanbanflow`
