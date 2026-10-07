

'''
Voice Agent
│
├── Operational state
│   ├── calls
│   ├── users
│   ├── sessions
│   ├── transcripts
│   ├── tools
│   └── appointments
│
└── Long-term memory
    ├── preferences
    ├── facts about user
    ├── previous conversations
    ├── relationships
    └── behavioral patterns

'''

'''


I'd start with Mem0 for your experiment because its open-source version lets you inspect/use the architecture more directly. Then:
1. Integrate Mem0 into your Voice Agent.
2. Test real conversations and memory retrieval.
3. Observe what it stores, when it stores it, and what it retrieves.
4. Replace Mem0 with your own implementation piece-by-piece.
5. Compare your system against Mem0/Supermemory.

'''

#? Two rules for Ava, whichever you choose:

# Bookings are not memory. Keep them in Google Calendar plus a small ledger table, because exact IDs and times can't be left to LLM-extracted memories.
# Keep memory off the hot path. Load a user's memories once at session start, and write new ones in a background task after the turn. No memory search 
  #inside the 0.6 to 0.9 s reply budget.

#! Note : Current Mem0 open source version doesnot have the Grapgh memory , 
# either build it urself or use a different source 

