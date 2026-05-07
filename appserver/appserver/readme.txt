
list of services and programs that run to implement tradewave


--------------------------------------------
API server:
--------------------------------------------
appserver.py
account_service.py
trade_processor.py

One Time software running by crontab periodically:

update_canceled_orders.py
data_updater... 

--------------------------------------------
Web Server:
--------------------------------------------
blog_processor.py
blog_queue.py

One Time software running by crontab:

generate_emails_sr.py 
top10_jobs_today_to_queue_cron
m_facebook.py

--------------------------------------------
key provider:
--------------------------------------------
logcollector.py
keyprovider.py
stockscore.py



--------------------------------------------
Note about Bitcoin
--------------------------------------------
Bitcoin symbol and name has 0x in front of it.
it doesn't work with analytics for some reason
I had to remove 0x but EOD requires it in the symbol
has to make sure that works 5/21/2024





