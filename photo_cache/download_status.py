"""Describe actual downloader stages without treating animation as progress."""

from .connection_status import local_date

ACTIVE_PHASES = {'connecting', 'reading_albums', 'downloading'}


def activity_text(state: dict, running: bool) -> str:
    activity = state.get('download_activity', {})
    phase = activity.get('phase')
    if running and phase == 'connecting':
        return 'Connecting to Google Photos…'
    if running and phase == 'reading_albums':
        return 'Reading selected albums… No photos are being downloaded yet.'
    counts = (f"{activity.get('added', 0)} added · {activity.get('skipped', 0)} skipped · "
              f"{activity.get('failed', 0)} failed")
    if running and phase == 'downloading':
        return f"Downloading: photo {activity.get('current', 0)} of {activity.get('total', 0)} · {counts}"
    if phase in ACTIVE_PHASES:
        return 'Previous download stopped before finishing · ' + counts
    if state.get('last_error'):
        stamp = local_date(state.get('last_attempt'))
        return 'Idle · Last download issue' + (f' ({stamp})' if stamp else '') + ': ' + state['last_error']
    if phase == 'finished' or (phase == 'waiting' and activity.get('total')):
        return 'Idle · Last batch: ' + counts
    return 'Idle · No photo download is running.'
