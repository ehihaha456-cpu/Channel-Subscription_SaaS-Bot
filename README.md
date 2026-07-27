Business Automation Batch 3

Changed files:
- handlers/seller.py
- database/seller_data.py

Implemented:
- Expanded Business Automation settings screen
- Automation, Welcome Once, Ignore Own Messages, Anti-loop and Flood Protection toggles
- Working-hours enable/disable and HH:MM/timezone editor
- Shared reply-delay editor
- Action-button mode selector: Open Clone Bot or Stay in Account Chat
- Expanded statistics fields for conversations and Plans/Renew/Profile/Referral actions
- Refresh button for statistics
- Database helper for safe per-account statistic increments

Note:
The MTProto message-processing worker must call increment_business_account_stat when it sends messages or handles action buttons. This batch adds the configuration and database/statistics foundation without changing existing clone-bot behavior.
