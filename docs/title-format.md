# RuTracker title format

Reference for the title parser. Paraphrased from RuTracker's section rules (not copied);
real titles deviate, so the parser is tolerant and the rules are the target, not a guarantee.
Test corpus: `backend/tests/data/search/*.json` (real search exports).

## Anime

Source: «Правила раздела «Аниме»», https://rutracker.org/forum/viewtopic.php?t=1992731
(edition of 2025-12-19, §6.2 title format, §3 release assembly, §5 duplicates).

### Grammar

```
Russian / Romaji / Other names (Director) [type] [count] [languages] [hardsub] [year, genres, quality, HDR] [other tags]
```

Components may be omitted, but the order is fixed. Observed deviations: missing spaces
between brackets, `(…)` instead of `[…]`, a trailing `.` after the year, release-group or
dubber names in the title (forbidden, but present in old topics), typos (`[Субитры]`).

### Names

- `/`-separated. First: one Russian name (licensed title if any). Second: romaji (AniDB
  spelling preferred). Then any alternatives (English, other Russian names) — use all of them
  for matching.
- Season marker after the Russian name: `(ТВ-N)` / `(ОВА-N)`, and for split cours
  `(ТВ-N, часть M)` (parts are separate topics). Not merged with the type tag.
- Director in Russian in `(…)` after the names, optional — not a season marker.
- Romaji/English names carry their own season hints: `2nd Season`, `Season 2`, a trailing
  ` 2`, or a sequel subtitle (`2-Choume`) — fall back to the year vs TVDB/TMDb air years.

### Type

`Movie`, `TV`, `OVA`, `ONA`, `Special`; combined with specials as `TV+Special`,
`Movie+Special`.

### Episode count

Omitted for single-episode works.

| Form | Meaning |
|---|---|
| `[24 из 24]` | all 24 |
| `[1-12 из 24]`, `[2-8 из 24]` | a range |
| `[серия 10 из 24]` | one episode |
| `[1-45 из >45]` | ongoing, total unknown |
| `[12+1 из 12+1]` | episodes + specials (with `TV+Special`) |
| `[1-10+1 из 12+2]` | ranges with specials |
| `[1+1]` | two episodes of different types |

Also seen: `[16/16]`.

### Languages

`[RUS(int|ext), other audio…, JAP+Sub]`:

- `RUS` — Russian voice track; `(int)` inside the container, `(ext)` external file (no suffix
  for DVD discs). The voice **type** (dub / MVO / DVO / VO) is *not* in the title — the rules
  put it in the description, and dubber names are banned from the title. Needs the topic page.
- `ENG`, `CHI`, `KOR`, `DEU`, `FRA`, … — other audio tracks. `JAP` — Japanese audio.
- `Sub` — **toggleable Russian subtitles**. Subtitles in other languages are never indicated.
  So `JAP+Sub` = original audio + Russian subs; English subs are invisible in anime titles.
- Track counts are not marked in video topics. (The audio-tracks subsection uses `RUS(3*MVO)`.)
- Delayed external dubs split the block into groups joined with `&`, each with its own count:
  `[TV+Special] [10+11 из 10+11] [JAP+Sub] & [10+0 из 10+11] [RUS(ext)]`.
- Every video topic must carry a Russian translation (subs or voice); untranslated releases
  only as approved rarities.
- "Universal release" = original audio + Russian voice + Russian subs.

### Hardsub (only when present)

`[хардсаб]` burned-in subs · `[полухардсаб]` burned-in signs/karaoke/logos, dialogue clean ·
`[русский хардсаб]` burned-in Russian subs (then it must be the only translation).

### Year, genres, quality, HDR

- Year first (a list of years is allowed for film series, ranges like `2007-2009`), genres may
  be dropped, then quality, then HDR.
- Quality: the SD-cinema list (BDRip, BDRemux, Blu-Ray, WEB-DL, WEBRip, HDTVRip, DVDRip,
  DVD5/9, …). WEB-DLRip is written as WEBRip; HDRip is not used for downscales.
- HDR (only when present, no `SDR` tag): `HDR10`, `HDR10+`, `HLG`, `Dolby Vision TV`
  (profile 5 in MP4), `Dolby Vision`; compatible combos listed together
  (`HDR10, HDR10+, Dolby Vision`).

### Other tags

- Resolution: `720p`, `810p`, `960p`, `1080p`, `2160p` (`i` for interlaced).
- Edition: `Локализованный видеоряд`, `Режиссерская версия / Director's Cut`,
  `Расширенная версия / Extended Cut`, `Театральная версия / Theatrical Cut`,
  regional cuts (`американская версия`, …).
- Player subsection: `[HD]` (H.264, hardware-player safe), `[HWP]` (DivX/XviD).

### Releases and topics

- One topic = one season of one work (collections of different works or seasons are banned);
  specials that belong to the season may be included.
- Completed seasons are consolidated: ≤30 episodes in one topic, longer seasons in chunks of
  ≥20 episodes.
- Ongoing topics are updated in place (same topic, re-uploaded torrent).
- Superseded releases move to «Архив (Аниме)».

### Subsections

Video (candidates for results): Онгоинги (HD Video), Аниме (HD Video) `1105`,
Аниме (DVD Video), Аниме (SD Video) `1389`, Аниме (плеерный подраздел) `1391`,
Аниме (QC подраздел) `2491` (dubs with complaints/unknown dubbers), franchise subsections
Ван-Пис / Гандам / Наруто / Покемоны (any quality), Дунхуа и Эни (Chinese/Korean animation),
Архив (Аниме) `535` (superseded).

Not video: Звуковые дорожки и Переводы (Аниме) `809`, Артбуки и журналы, Обои, сканы,
аватары, арт `1386`, AMV и другие ролики, soundtracks `282` / `1388` / `1397`, manga
`281` / `2465`. Forum ids still to collect for the rest.

## Foreign cinema (Зарубежное кино)

Sources: «Правила раздела Зарубежное кино» and the template topic «Оформления раздачи»
(https://rutracker.org/forum/viewtopic.php?t=3253741: title order, translation abbreviations;
rules from 2010-03-29, corrected 2011-09-14). These are the SD film rules; the HD Video and
TV-series sections have their own (still to read).

### Grammar

```
Russian / Original (Режиссёр / Director) [year, country, genres, quality] [extra] translations
```

- Russian name first (both if there are two variants), then the English/original name.
  Never original-first; no leading digits, quotes or studio names unless part of the title.
- Director in Russian **and** English (optionally also the original language), `/`-separated,
  in `(…)`. Same parenthesis shape as the anime director — not a season marker.
- Bracket: year (`2008`, `2008 г.`, `2008г`), country, at least one genre, then quality.
- Quality gets the codec suffix `-AVC` (mandatory for H.264/AVC/VC-1: `BDRip-AVC`,
  `HDRip-AVC`, `DVDRip-AVC`) or optional `-ASP` (XviD/DivX). Disc counts: `2 х DVD9`.
- Extra info only at the end: edition (`[Расширенная версия / Unrated version]`,
  `Режиссерская версия`), publisher, source, `Superbit` and the like.
- Collections: series name, year range `[1962 - 2006 г., …]`, `24 фильма`.
- Silent films: `[Немое кино] интертитры (Rus, Eng)`.

### Translations in the title

All translations in the release, joined with ` + `, after the brackets:

| Abbreviation | Meaning |
|---|---|
| `Dub` | dubbed (professional, or pseudo-dub by internet studios) |
| `MVO (…)` | multi-voice voice-over, 3+ voices |
| `DVO (…)` | two-voice voice-over |
| `AVO (Author)` | author's single voice-over, only when the author is known |
| `VO (…)` | other single-voice (studio, unknown author, voiced by someone else) |
| `Original` | the original-language audio track |
| `Sub (Rus, Eng, …)` | subtitles, languages listed |

- `(…)` after an abbreviation is identifying info: studio / source / performer / publisher
  (`MVO (Киномания)`, `MVO (Twister)`, `AVO (Гаврилов)`), possibly `performer / author`.
  Parentheses may be dropped: `AVO Володарский`, `Sub Rus, Ukr, Eng, Fra`.
- A non-Russian translation carries its language: up to 4 Latin letters in parentheses,
  `MVO (Ukr)`. No language marker means Russian. Telling `(Ukr)` from a studio name needs a
  list of language codes.
- Same-type translations may be merged when the title is too long:
  `AVO (Гаврилов, Сербин, Живов)`.
- **Titles are capped at 101 characters**; when it doesn't fit, genres are cut first, then
  translations may be listed partially or dropped entirely. A missing `Original` or `Sub`
  in a long title does not prove absence — the topic page is authoritative.
- Example: `Схватка / Heat (Майкл Мэнн / Michael Mann) [1995 г., Боевик, DVDRip] MVO (Twister) + MVO (Gemini) + MVO (Ukr) + MVO (Карусель) + AVO (Goblin) + AVO (Гаврилов) + AVO (Живов) + VO + Sub (Eng, Rus)`.

### Translation fields (topic description, not the title)

Standardised `Перевод:` / `Перевод N:` lines, plus `Субтитры:` and `Оригинальная аудиодорожка:`.
This is where the voice type and subtitle languages come from on the topic page:

| `Перевод:` value | Voice type |
|---|---|
| `Профессиональный (дублированный)`, `Профессиональный (псевдодублированный)`, `Любительский (псевдодублированный)` | Dub |
| `Профессиональный (многоголосый закадровый)`, `Любительский (многоголосый закадровый)` | MVO (3+ voices) |
| `Профессиональный (двухголосый закадровый)`, `Любительский (двухголосый закадровый)` | DVO |
| `Авторский (одноголосый закадровый) <name>` | AVO (only names from RuTracker's approved list of author translators) |
| `Студийный (одноголосый закадровый) <studio>` | VO (studio) |
| `Одноголосый закадровый` | VO |
| `Субтитры` | subtitles only |
| `не требуется` | no translation needed (silent films, foreign films shot in Russian) |

Followed by an optional source (Лицензия, a studio or channel name).
`Субтитры:` lists languages in words (`русские, украинские, английские, немецкие`, or `нет`),
so English subtitles are detectable from the topic page even when the title says nothing.
Machine-translated subtitles and text-to-speech voice-overs are banned.

### Quality designations

From the shared quality post (https://rutracker.org/forum/viewtopic.php?p=27840514), also
referenced by the anime rules: `CamRip`/`CAM`, `Telesync`/`TS`, `Telecine`/`TC`, `Screener`/`SCR`,
`DVDScr`, `Workprint`/`WP`, `VHSRip`, `LDRip`, `TVRip`, `DVB`, `DVDRip`, `DVD5`/`DVD9`,
`DVDRemux`, `HDTV`, `HDTVRip`, `WEB-DL`, `WEB-DLRip`, `WEBRip`, `HDRip`, `BDRip`, `BDRemux`,
`Blu-Ray`, `HD-DVD`, `HDDVDRip`, `DTheaterRip`.

- `HDRip` means a rip from an HD rip (or with an unverified source); `BDRip` requires a known
  Blu-ray / BD Remux source.
- The source is never in the title (only in the description).

## HD / UHD Video subsections (films and series)

Source: «Правила подразделов (U)HD Video» (edition 2025-01-20), §5.1. Same title shape as the
film rules, plus:

- Resolution / scan tag after the quality, inside the bracket: `720p`, `1080p`, `1080i`,
  `2160p` (`BDRemux 1080p`, `WEB-DL 2160p`, `HDTV 1080i`).
- HDR after the resolution: `HDR10`, `HDR10, HDR10+`, `HLG`, `SDR` (used here, unlike anime),
  `Dolby Vision, HDR10, HDR10+`, `Dolby Vision, HDR10`, `Dolby Vision` (MKV, not HDR10
  compatible), `Dolby Vision TV` (MP4).
- Rebuilt discs: `Blu-ray disc (custom)`, optionally `BD25` / `BD50`.
- Translation counts and languages without parentheses:
  `Dub + 2x MVO + 2x DVO + 2x Ukr + Sub Rus, Ukr, Eng + Original Eng`,
  `2x Dub + 2x MVO + DVO + 3x AVO + VO + 3x MVO Ukr + Sub Rus, Eng + Original Eng`,
  `Dub + 3х MVO (Jaskier, TVShows, LostFilm)` — note the Cyrillic `х` also appears.
  `2x Ukr` = two Ukrainian tracks of unstated type. `Original Eng` names the original language.
- Russian-made films: `Чужие письма (Илья Авербах) [1975, СССР, мелодрама, драма, HDTV 1080i] Original Rus`
  — Russian title only, no translation; subtitles (`Sub Eng`) would appear as `+ Sub …`.

## Russian series (Русские сериалы)

Source: «Правила раздела Русские сериалы» (updated 2026-10-09).

```
Russian title / Сезон: 1-5 / Серии: 1-60 из 60 (Directors) [years, genres, quality resolution]
```

- `Сезон: N` or a range, `Серии: X-Y из Z`; ongoing topics grow in place.
- Up to three directors (`… и др.`), years may be a range `1998-2004`.
- No translation or subtitle info in the title (Russian original); subtitles are only in the
  description.
- Russian films (Наше кино) follow the general template; no subtitle convention in titles.

## Parser approach

The sections share one vocabulary; the difference is mostly *where* languages are written.
One tolerant, token-based parser for all sections, with the forum id as a hint only:

1. Names: everything before the first `[`, split on ` / `; strip the director `(…)`, season
   markers `(ТВ-N)` / `(ОВА-N)` / `Сезон: …` / `Серии: …`.
2. Brackets: type (`TV`, `Movie`, …), counts (`[N из M]`, `[1-10+1 из 12+2]`, `[16/16]`),
   anime language groups (`[RUS(int), JAP+Sub] & […]`), hardsub, the year/genre/quality
   bracket (quality + `-AVC`/`-ASP`, resolution, HDR), editions.
3. Trailing translations (film/series style): split on ` + `; each item
   `[N x|х] (Dub|MVO|DVO|AVO|VO|<Lang>) [Lang] [(info)]`, `Original [Lang]`, `Sub [(]langs[)]`.
4. Unknowns are kept, not guessed: a release without parsed language info is "unknown,
   check the topic page", never "no original audio".

- `RTA-QC`: the topic is in a QC subsection ("Аниме (QC подраздел)": releases with complaints, e.g. unknown dubbers). Custom format "RuTrackarr · QC subsection" (`docs/arr-custom-formats.json`) — give it a small negative score.
