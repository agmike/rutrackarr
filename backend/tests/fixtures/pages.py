"""Hand-written RuTracker-like pages (structure as the site serves it).

Real captured pages (scrubbed of account details) will replace these.
"""

LOGGED_IN_HEADER = '<div id="logged-in-username">tester</div>'

LOGIN_FORM = """<html><body><form action="login.php" method="post">
<input name="login_username"><input name="login_password" type="password">
<input type="submit" name="login" value="вход"></form></body></html>"""

LOGIN_FORM_CAPTCHA = """<html><body><form action="login.php" method="post">
<img src="https://static.rutracker.cc/captcha/abc/123.jpg" alt="pic">
<input type="hidden" name="cap_sid" value="SID123">
<input type="text" name="cap_code_deadbeef" value="">
<input name="login_username"><input name="login_password" type="password">
</form></body></html>"""

LOGIN_WRONG = (
    """<html><body><h4 class="warnColor1 tCenter mrg_16">неверный пароль</h4>
"""
    + LOGIN_FORM
    + "</body></html>"
)

INDEX_LOGGED_IN = f"<html><body>{LOGGED_IN_HEADER}<p>index</p></body></html>"


def search_page(rows: str, logged_in: bool = True) -> str:
    head = LOGGED_IN_HEADER if logged_in else ""
    return f"""<html><body>{head}<table id="tor-tbl"><tbody>{rows}</tbody></table></body></html>"""


ROW_HYOUKA = """<tr class="tCenter hl-tr" data-topic_id="4211111">
<td class="row1 t-ico"><span class="tor-icon tor-approved" title="проверено">&radic;</span></td>
<td class="row1 t-ico"></td>
<td class="row1 f-name-col"><div class="f-name"><a class="gen f" href="tracker.php?f=1105">Аниме (HD Video)</a></div></td>
<td class="row4 med tLeft t-title-col tt"><div class="wbr t-title"><a class="med tLink tt-text ts-text hl-tags bold" href="viewtopic.php?t=4211111">Хёка / Hyouka [TV] [22 из 22] [RUS(ext), JAP+Sub] [2012, повседневность, BDRip] [720p]</a></div></td>
<td class="row1 u-name-col"><div class="wbr u-name"><a class="med ts-text" href="tracker.php?pid=1">uploader1</a></div></td>
<td class="row4 small nowrap tor-size" data-ts_text="15032385536"><a class="small tr-dl dl-stub" href="dl.php?t=4211111">14 GB</a></td>
<td class="row4 nowrap" data-ts_text="42"><b class="seedmed">42</b></td>
<td class="row4 leechmed bold" title="Личи">3</td>
<td class="row4 small number-format">1 234</td>
<td class="row4 small nowrap" data-ts_text="1700000000"><p>14-Ноя-23</p></td>
</tr>"""

ROW_NOT_FOUND = '<tr><td class="row1 tCenter pad_8" colspan="10">Не найдено</td></tr>'

# Title split across highlight/wbr elements, as RuTracker marks up search hits.
ROW_SPLIT_TITLE = """<tr class="tCenter hl-tr"><td class="row1 t-ico"></td><td class="row1 t-ico"></td>
<td class="row1 f-name-col"><div class="f-name"><a class="gen f" href="tracker.php?f=1105">Аниме (HD Video)</a></div></td>
<td class="row4 t-title-col"><div class="t-title"><a class="tLink" href="viewtopic.php?t=6000001">Городская демонесса (ТВ-2) / <b>Machikado</b> <b>Mazoku</b> 2-Choume / The Demon Girl Next Door 2 <wbr>[TV] [12 из 12] [JAP+Sub] [2022, Комедия, BDRemux] [1080p]</a></div></td>
<td class="row1 u-name-col"><a href="#">up</a></td>
<td class="row4 tor-size" data-ts_text="1000"><a class="tr-dl" href="dl.php?t=6000001">1 KB</a></td>
<td data-ts_text="5"><b class="seedmed">5</b></td><td class="leechmed">0</td><td>1</td><td data-ts_text="1700000000">x</td></tr>"""

MAINTENANCE = """<html><head><title>rutracker.org</title></head><body>
<div class="msg-main">Форум временно отключен на профилактические работы до 04:45 MSK</div></body></html>"""
