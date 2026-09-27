"""Local serial input preparation while API run proceeds. No API/network."""
import time
from pathlib import Path
import native_zh

HERE = Path(__file__).resolve().parent
TERMINAL = {'completed', 'finished_with_terminal_failures', 'blocked'}


def main():
    marker = HERE / 'translations/ALL_INPUTS_PREPARED'
    if marker.exists():
        raise FileExistsError('Translation input preparation already finalized')
    while True:
        native_zh.prepare()
        state = native_zh.core.read(HERE / 'run/run_state.json', {})
        if state.get('status') in TERMINAL:
            native_zh.prepare()  # terminal state is written after the last record
            native_zh.core.dump(marker, {'run_status': state['status'],
                 'scope': 'All currently obtainable English/public/failure text; no missing model output fabricated.',
                 'finalized_at': time.time()})
            print('ALL_INPUTS_PREPARED', state['status'], flush=True)
            return
        time.sleep(30)


if __name__ == '__main__':
    main()
