---
type: community
cohesion: 0.16
members: 26
---

# User Chat API

**Cohesion:** 0.16 - loosely connected
**Members:** 26 nodes

## Members
- [[A single message in a conversation. Persisting these is what makes chat history…]] - rationale - backend/models.py
- [[BaseModel_2]] - code
- [[ChatMessage]] - code - backend/models.py
- [[Conversation]] - code - backend/models.py
- [[One chat thread. A user can have many — this is what the 'New Chat' tabs in the…]] - rationale - backend/models.py
- [[Question]] - code - backend/routes/user_routes.py
- [[Session_3]] - code
- [[Streams the answer back as newline-delimited JSON (NDJSON) instead of waiting…]] - rationale - backend/routes/user_routes.py
- [[_message_images()]] - code - backend/routes/user_routes.py
- [[_serialize_conversation()]] - code - backend/routes/user_routes.py
- [[_validate_images()]] - code - backend/routes/user_routes.py
- [[ask_question()]] - code - backend/routes/user_routes.py
- [[base64]] - concept
- [[create_conversation()]] - code - backend/routes/user_routes.py
- [[delete_1]] - code
- [[delete_conversation()]] - code - backend/routes/user_routes.py
- [[event_stream()]] - code - backend/routes/user_routes.py
- [[fastapi_responses]] - concept
- [[get_5]] - code
- [[get_conversation_messages()]] - code - backend/routes/user_routes.py
- [[get_progress()]] - code - backend/routes/user_routes.py
- [[get_queue_status()]] - code - backend/routes/user_routes.py
- [[list_conversations()]] - code - backend/routes/user_routes.py
- [[post_3]] - code
- [[queue_status()]] - code - backend/rag.py
- [[user_routes.py]] - code - backend/routes/user_routes.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/User_Chat_API
SORT file.name ASC
```

## Connections to other communities
- 9 edges to [[_COMMUNITY_Authorization and Database Setup]]
- 8 edges to [[_COMMUNITY_Topic Classification]]
- 4 edges to [[_COMMUNITY_Subject Data Management]]
- 4 edges to [[_COMMUNITY_Retrieval Augmented Generation]]
- 4 edges to [[_COMMUNITY_User Progress Tracking]]
- 3 edges to [[_COMMUNITY_Application Startup and Migrations]]
- 1 edge to [[_COMMUNITY_Learning Progress Tests]]
- 1 edge to [[_COMMUNITY_Branch Classifier Tests]]
- 1 edge to [[_COMMUNITY_School Management API]]
- 1 edge to [[_COMMUNITY_Adaptive Difficulty Model]]

## Top bridge nodes
- [[user_routes.py]] - degree 35, connects to 10 communities
- [[ask_question()]] - degree 13, connects to 3 communities
- [[Conversation]] - degree 10, connects to 2 communities
- [[ChatMessage]] - degree 8, connects to 2 communities
- [[get_progress()]] - degree 5, connects to 2 communities