---
type: community
cohesion: 0.32
members: 13
---

# Notification API

**Cohesion:** 0.32 - loosely connected
**Members:** 13 nodes

## Members
- [[Notification]] - code - backend/models.py
- [[One entry in an admin's bell. notify_admins() (notifications.py) writes them;…]] - rationale - backend/models.py
- [[Session_10]] - code
- [[The admin bell what the AI wasn't sure about, uploads by teachers, deleted…]] - rationale - backend/routes/notification_routes.py
- [[_mine()]] - code - backend/routes/notification_routes.py
- [[clear_notifications()]] - code - backend/routes/notification_routes.py
- [[delete_4]] - code
- [[get_10]] - code
- [[list_notifications()]] - code - backend/routes/notification_routes.py
- [[mark_all_read()]] - code - backend/routes/notification_routes.py
- [[mark_read()]] - code - backend/routes/notification_routes.py
- [[notification_routes.py]] - code - backend/routes/notification_routes.py
- [[post_9]] - code

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Notification_API
SORT file.name ASC
```

## Connections to other communities
- 7 edges to [[_COMMUNITY_Authorization and Database Setup]]
- 6 edges to [[_COMMUNITY_Topic Classification]]
- 2 edges to [[_COMMUNITY_Application Startup and Migrations]]
- 1 edge to [[_COMMUNITY_Administrator API]]
- 1 edge to [[_COMMUNITY_Subject Data Management]]
- 1 edge to [[_COMMUNITY_School Management API]]
- 1 edge to [[_COMMUNITY_Learning Progress Tests]]

## Top bridge nodes
- [[notification_routes.py]] - degree 17, connects to 5 communities
- [[Notification]] - degree 10, connects to 3 communities
- [[_mine()]] - degree 8, connects to 1 community
- [[list_notifications()]] - degree 6, connects to 1 community
- [[mark_all_read()]] - degree 6, connects to 1 community