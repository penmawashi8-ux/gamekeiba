"""Write now+1min (JST) to _tmp_st.txt for use by auto_start.bat"""
from datetime import datetime, timedelta, timezone

jst = timezone(timedelta(hours=9))
t = datetime.now(jst) + timedelta(minutes=1)
with open("_tmp_st.txt", "w") as f:
    f.write(t.strftime("%Y-%m-%dT%H:%M:%S+09:00"))
