from pathlib import Path

import streamlit as st


WORK_DIRECTORY_SESSION_KEY = "work_directory_name"


def _remember_work_directory(widget_key: str) -> None:
	st.session_state[WORK_DIRECTORY_SESSION_KEY] = st.session_state[widget_key]


def find_work_directories(responses_dir: Path) -> list[Path]:
	"""Return responses/ and its immediate responses_* subdirectories."""
	if not responses_dir.is_dir():
		return []
	return [
		responses_dir,
		*sorted(
			path
			for path in responses_dir.glob("responses_*")
			if path.is_dir()
		),
	]


def select_work_directory(
	responses_dir: Path,
	widget_key: str,
) -> Path | None:
	"""Show the shared work-directory selector and return its selected path."""
	work_directories = find_work_directories(responses_dir)
	if not work_directories:
		return None

	directories_by_name = {
		path.name: path for path in work_directories
	}
	directory_names = list(directories_by_name)
	selected_name = st.session_state.get(WORK_DIRECTORY_SESSION_KEY)
	if selected_name not in directory_names:
		selected_name = responses_dir.name
	st.session_state[widget_key] = selected_name

	selected_name = st.selectbox(
		"Selecciona el directorio de trabajo",
		directory_names,
		key=widget_key,
		on_change=_remember_work_directory,
		args=(widget_key,),
	)
	return directories_by_name[selected_name]
