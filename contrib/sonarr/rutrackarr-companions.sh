#!/bin/bash
# RuTrackarr companion tracks — a Sonarr custom script (Settings → Connect → Custom Script).
#
# RuTracker releases often carry external audio and subtitles in their own folders
# ("RUS Sound [Team]/…", "RUS Subs [Team]/…"); Sonarr doesn't import them. This script:
#   On File Import / Upgrade:  asks RuTrackarr which files of the torrent belong to the
#                              imported episode and hardlinks them next to it as
#                              <episode>.<lang>.<title>.<flags>.<ext> (Jellyfin/Plex/Kodi
#                              naming, e.g. "….ru.StudioBand.mka", "….ru.Team signs.forced.ass")
#   On Rename:                 moves them along with the episode
#   On Episode File Delete:    removes them (incl. when an upgrade replaces the episode)
#
# Downloads that didn't come from RuTrackarr are left alone. Needs bash and curl (both in the
# linuxserver Sonarr image). Settings, from the environment or rutrackarr-companions.env
# next to this script:
#   RUTRACKARR_URL      e.g. http://rutrackarr:8787/rutrackarr
#   RUTRACKARR_API_KEY  the Torznab API key
set -uo pipefail

here=$(dirname "$(readlink -f "$0")")
# shellcheck source=/dev/null
[ -f "$here/rutrackarr-companions.env" ] && . "$here/rutrackarr-companions.env"

RUTRACKARR_URL="${RUTRACKARR_URL:-}"
RUTRACKARR_API_KEY="${RUTRACKARR_API_KEY:-}"

log() { echo "rutrackarr-companions: $*" >&2; }

# Sonarr's variable names, in either case.
var() {
	local n v
	for n in "$@"; do
		v="${!n:-}"
		if [ -n "$v" ]; then
			printf '%s' "$v"
			return
		fi
	done
}

EXTS=" mka ac3 eac3 dts aac flac m4a mp3 opus thd wav ass ssa srt sup vtt sub idx "
is_companion() {
	local ext="${1##*.}"
	[[ "$EXTS" == *" ${ext,,} "* ]]
}

# Companion files of a video: "<video path without extension>.<anything>.<companion ext>".
# Compared as strings — episode names are full of [] that globbing would misread.
companions_of() {
	local video="$1" base="${1%.*}" f
	for f in "${1%/*}"/*; do
		if [[ "$f" == "$base".* && "$f" != "$video" ]] && is_companion "$f"; then
			printf '%s\n' "$f"
		fi
	done
}

link() {
	local src dst id plan path suffix root="" from to
	src=$(var sonarr_episodefile_sourcepath Sonarr_EpisodeFile_SourcePath)
	dst=$(var sonarr_episodefile_path Sonarr_EpisodeFile_Path)
	id=$(var sonarr_download_id Sonarr_Download_Id)
	[ -n "$src" ] && [ -n "$dst" ] && [ -n "$id" ] && [ -n "$RUTRACKARR_URL" ] || return 0
	if ! plan=$(curl -fsS --max-time 30 -G "${RUTRACKARR_URL%/}/torznab/companions" \
		--data-urlencode "hash=$id" --data-urlencode "source=$src" \
		--data-urlencode "apikey=$RUTRACKARR_API_KEY" 2>/dev/null); then
		return 0 # not a RuTrackarr download (or RuTrackarr unreachable): nothing to do
	fi
	while IFS=$'\t' read -r path suffix; do
		[ -n "$path" ] || continue
		if [ "$path" = "#video" ]; then
			root="${src%"$suffix"}" # the torrent's folder: source path minus the video's path in it
			if [ "$root" = "$src" ]; then
				log "source $src doesn't end with $suffix — skipped"
				return 0
			fi
			continue
		fi
		[ -n "$root" ] || continue
		from="$root$path"
		to="${dst%.*}.$suffix"
		if [ ! -f "$from" ]; then
			log "missing $from"
			continue
		fi
		if ln -f "$from" "$to" 2>/dev/null || cp -f "$from" "$to"; then
			log "linked $to"
		fi
	done <<<"$plan"
}

rename() {
	local -a prev new
	local i old nw f
	IFS='|' read -r -a prev <<<"$(var sonarr_episodefile_previouspaths Sonarr_EpisodeFile_PreviousPaths)"
	IFS='|' read -r -a new <<<"$(var sonarr_episodefile_paths Sonarr_EpisodeFile_Paths)"
	for i in "${!prev[@]}"; do
		old="${prev[$i]}"
		nw="${new[$i]:-}"
		[ -n "$old" ] && [ -n "$nw" ] || continue
		while IFS= read -r f; do
			[ -n "$f" ] || continue
			mv -f "$f" "${nw%.*}${f#"${old%.*}"}" && log "moved $f"
		done < <(companions_of "$old")
	done
}

remove() {
	local p f
	p=$(var sonarr_episodefile_path Sonarr_EpisodeFile_Path)
	[ -n "$p" ] || return 0
	# An upgrade that kept the same name: the new episode is already there and gets its own
	# companions linked on import — don't remove them.
	[ -e "$p" ] && return 0
	while IFS= read -r f; do
		[ -n "$f" ] || continue
		rm -f "$f" && log "removed $f"
	done < <(companions_of "$p")
}

case "$(var sonarr_eventtype Sonarr_EventType)" in
Test)
	: "${RUTRACKARR_URL:?RUTRACKARR_URL is not set}" "${RUTRACKARR_API_KEY:?RUTRACKARR_API_KEY is not set}"
	curl -fsS --max-time 10 "${RUTRACKARR_URL%/}/torznab/api?t=caps" >/dev/null || {
		log "RuTrackarr not reachable at $RUTRACKARR_URL"
		exit 1
	}
	;;
Download) link ;;
Rename) rename ;;
EpisodeFileDelete) remove ;;
esac
exit 0
