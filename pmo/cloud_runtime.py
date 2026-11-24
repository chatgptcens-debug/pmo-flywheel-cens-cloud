"""Cloud demonstration: temporary data per Streamlit session; no operational connection."""
from pathlib import Path
import tempfile
import shutil
import sqlite3
from contextlib import closing

KEY = '_pmo_cloud_temp_v100'
SEED = Path(__file__).resolve().parents[1] / 'cloud_seed' / 'demo.sqlite3'

def prepare(state):
    if KEY not in state:
        workspace = tempfile.TemporaryDirectory(prefix='pmo-cloud-demo-')
        target = Path(workspace.name) / 'pmo_flywheel.sqlite3'
        try:
            shutil.copyfile(SEED, target)
            with closing(sqlite3.connect(target)) as con:
                if con.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise RuntimeError('Semilla de demostración inválida.')
            state[KEY] = workspace
        except Exception:
            workspace.cleanup()
            raise
    return Path(state[KEY].name)

def session_data_dir():
    import streamlit as st
    if KEY not in st.session_state:
        raise RuntimeError('No existe una sesión Cloud inicializada. No se permite conectar datos locales.')
    return Path(st.session_state[KEY].name)

def reset(state):
    workspace = state.pop(KEY, None)
    # Remove widget selections and cached IDs from the previous demo.
    for k in list(state.keys()):
        del state[k]
    if workspace is not None:
        workspace.cleanup()
