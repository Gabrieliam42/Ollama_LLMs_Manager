# Script Developer: Gabriel Mihai Sandu
# GitHub Profile: https://github.com/Gabrieliam42

import ctypes
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from ctypes import wintypes
from html import unescape
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup


PREFERRED_MODELS = ()
APP_NAME = "Ollama Library Models"
LIBRARY_URL = "https://ollama.com/library"
SEARCH_URL = "https://ollama.com/search"
SEARCH_QUERIES = ("abliterated", "uncensored", "derestricted")
MAX_SEARCH_PAGES = 100
TEXT_OUTPUT_FILENAME = "Ollama_LLMs_Installer.txt"
HTTP_TIMEOUT_SECONDS = 30
MAX_FETCH_WORKERS = 8
WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 860
DARK_ANTHRACITE_BLUE = "#151515"
DARK_ANTHRACITE_PANEL = "#0f0f0f"
DARK_ANTHRACITE_BORDER = "#2c2c2c"
DARK_BUTTON = "#252525"
DARK_BUTTON_ACTIVE = "#383838"
DARK_TEXT = "#f3f6f8"
DARK_MUTED_TEXT = "#c8d0d8"
BRIGHT_SUCCESS = "#1f7a4d"
BRIGHT_SUCCESS_ACTIVE = "#279d62"
MODEL_BADGES = (
    "tools",
    "thinking",
    "vision",
    "embedding",
    "completion",
    "audio",
    "cloud",
)
CATEGORY_SORT_PRIORITY = ("tools", "thinking", "vision", "embedding", "completion")
BADGE_STYLES = {
    "tools": {"background": "#1f7a4d", "foreground": "#ffffff"},
    "thinking": {"background": "#5f4bb6", "foreground": "#ffffff"},
    "vision": {"background": "#2468a8", "foreground": "#ffffff"},
    "embedding": {"background": "#b46a16", "foreground": "#101010"},
    "completion": {"background": "#575757", "foreground": "#ffffff"},
    "cloud": {"background": "#168a96", "foreground": "#ffffff"},
    "audio": {"background": "#a13f73", "foreground": "#ffffff"},
}


def get_app_base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent

    return Path(__file__).resolve().parent


def log_message(message):
    try:
        log_dir = get_app_base_dir() / ".cache"
        log_dir.mkdir(parents=True, exist_ok=True)
        with (log_dir / "Ollama.Library_LLMs.log").open(
            "a", encoding="utf-8", errors="replace"
        ) as log_file:
            log_file.write(f"{message}\n")
    except Exception:
        pass


def _hex_color_to_colorref(color):
    color = color.lstrip("#")
    red = int(color[0:2], 16)
    green = int(color[2:4], 16)
    blue = int(color[4:6], 16)
    return red | (green << 8) | (blue << 16)


def apply_dark_title_bar(window):
    if os.name != "nt":
        return

    try:
        window.update_idletasks()
        hwnd_value = int(window.winfo_id())
        hwnd_values = [hwnd_value]
        get_parent = ctypes.windll.user32.GetParent
        get_parent.argtypes = [wintypes.HWND]
        get_parent.restype = wintypes.HWND
        parent_hwnd = get_parent(wintypes.HWND(hwnd_value))
        if parent_hwnd and parent_hwnd not in hwnd_values:
            hwnd_values.append(parent_hwnd)

        for hwnd_value in hwnd_values:
            hwnd = wintypes.HWND(hwnd_value)
            dark_value = ctypes.c_int(1)
            for attribute_id in (20, 19):
                result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd,
                    attribute_id,
                    ctypes.byref(dark_value),
                    ctypes.sizeof(dark_value),
                )
                if result == 0:
                    break

            for attribute_id, color in (
                (34, DARK_ANTHRACITE_BLUE),
                (35, DARK_ANTHRACITE_BLUE),
                (36, DARK_TEXT),
            ):
                color_value = ctypes.c_int(_hex_color_to_colorref(color))
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd,
                    attribute_id,
                    ctypes.byref(color_value),
                    ctypes.sizeof(color_value),
                )
    except Exception:
        pass


def schedule_dark_title_bar(window):
    apply_dark_title_bar(window)
    for delay_ms in (0, 50, 250, 1000):
        window.after(delay_ms, lambda target=window: apply_dark_title_bar(target))


def isolate_tk_environment():
    if getattr(sys, "frozen", False):
        return

    for variable_name in ("TCL_LIBRARY", "TK_LIBRARY", "TCLLIBPATH"):
        os.environ.pop(variable_name, None)


def _candidate_paths():
    configured_path = os.environ.get("OLLAMA_EXE")
    if configured_path:
        yield Path(os.path.expandvars(configured_path)).expanduser()

    base_dir = get_app_base_dir()

    yield base_dir / "ollama.exe"
    yield base_dir / "Ollama" / "ollama.exe"

    resolved_from_path = shutil.which("ollama.exe") or shutil.which("ollama")
    if resolved_from_path:
        yield Path(resolved_from_path)

    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        yield Path(local_app_data) / "Programs" / "Ollama" / "ollama.exe"

    program_files = os.environ.get("ProgramFiles")
    if program_files:
        yield Path(program_files) / "Ollama" / "ollama.exe"

    program_files_x86 = os.environ.get("ProgramFiles(x86)")
    if program_files_x86:
        yield Path(program_files_x86) / "Ollama" / "ollama.exe"


def resolve_ollama_executable():
    for candidate in _candidate_paths():
        if candidate.is_file():
            return str(candidate)

    raise FileNotFoundError(
        "Could not locate ollama.exe. Set OLLAMA_EXE, place ollama.exe next to "
        "this script, add it to PATH, or install Ollama in a standard Windows location."
    )


def run_ollama_command(command):
    run_kwargs = {
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "check": True,
    }

    if os.name == "nt":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        run_kwargs["startupinfo"] = startupinfo
        run_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

    return subprocess.run(command, **run_kwargs)


def install_ollama_model(ollama_executable, model_name):
    # Use an empty prompt so Ollama can pull the model without entering
    # an interactive CLI session that would block the GUI.
    return run_ollama_command([ollama_executable, "run", model_name, ""])


def clean_text(text):
    return re.sub(r"\s+", " ", unescape(text or "")).strip()


def unique_values(*groups):
    merged_values = []
    seen_values = set()
    for group in groups:
        if not group:
            continue
        for value in group:
            normalized_value = clean_text(str(value))
            if not normalized_value or normalized_value in seen_values:
                continue
            merged_values.append(normalized_value)
            seen_values.add(normalized_value)
    return tuple(merged_values)


def class_list_contains(value, *expected_classes):
    if not value:
        return False

    if isinstance(value, str):
        class_values = value.split()
    else:
        class_values = value

    return all(expected_class in class_values for expected_class in expected_classes)


def first_nonempty(*values):
    for value in values:
        if value:
            return value
    return ""


def parse_integer(text):
    match = re.search(r"\d+", clean_text(text))
    if match is None:
        return 0
    return int(match.group(0))


def parse_human_number(text):
    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*([kmbt]?)", clean_text(text), re.I)
    if match is None:
        return -1.0

    unit_multipliers = {
        "": 1,
        "K": 1_000,
        "M": 1_000_000,
        "B": 1_000_000_000,
        "T": 1_000_000_000_000,
    }
    value = float(match.group(1))
    unit = match.group(2).upper()
    return value * unit_multipliers.get(unit, 1)


def normalize_model_badges(model_name, detected_badges):
    badges = {clean_text(badge).casefold() for badge in detected_badges if badge}
    if re.search(r"(^|[:/_\-.])cloud($|[:/_\-.])", model_name.casefold()):
        badges.add("cloud")

    return tuple(badge for badge in MODEL_BADGES if badge in badges)


def fetch_html(url):
    request = Request(
        url,
        headers={
            "User-Agent": f"{APP_NAME}/1.0",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    with urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def get_soup(url):
    return BeautifulSoup(fetch_html(url), "html.parser")


def extract_badges_and_sizes(chip_container, model_name):
    badges = []
    sizes = []
    if chip_container is None:
        return (), ()

    for chip in chip_container.find_all("span", recursive=False):
        chip_text = clean_text(chip.get_text(" ", strip=True))
        if not chip_text:
            continue

        lowered_chip = chip_text.casefold()
        if lowered_chip in MODEL_BADGES:
            badges.append(lowered_chip)
        else:
            sizes.append(chip_text)

    return normalize_model_badges(model_name, badges), unique_values(sizes)


def extract_summary_text(soup):
    summary_content = soup.find(id="summary-content")
    if summary_content is None:
        return ""

    return clean_text(summary_content.get_text(" ", strip=True))


def extract_page_model_count(soup):
    for paragraph in soup.find_all("p"):
        paragraph_text = clean_text(paragraph.get_text(" ", strip=True))
        match = re.fullmatch(r"(\d+)\s+models?", paragraph_text, re.I)
        if match is not None:
            return int(match.group(1))

    return 0


def build_model_display(model_entry):
    display_parts = [model_entry["name"]]
    if model_entry["downloads"]:
        display_parts.append(f"[{model_entry['downloads']} pulls]")
    if model_entry["tag_count"]:
        display_parts.append(f"[{model_entry['tag_count']} tags]")
    if model_entry["badges"]:
        display_parts.append(" ".join(f"[{badge}]" for badge in model_entry["badges"]))
    return "  ".join(display_parts)


def get_model_category_rank(model_entry):
    model_badges = set(model_entry["badges"])
    ordered_categories = (
        "tools",
        "thinking",
        "vision",
        "embedding",
        "completion",
        "audio",
        "cloud",
    )
    for category_rank, badge_name in enumerate(ordered_categories):
        if badge_name in model_badges:
            return category_rank

    return len(ordered_categories)


def extract_tag_name(model_name):
    name_parts = model_name.split(":", maxsplit=1)
    if len(name_parts) != 2:
        return ""
    return name_parts[1].strip()


def is_allowed_quantization(tag_name):
    quantization_match = re.search(r"(q\d+(?:_[a-z0-9]+)*)$", tag_name, re.I)
    if quantization_match is None:
        return True

    quantization = quantization_match.group(1).upper()
    if quantization.startswith(("Q1", "Q2", "Q3")):
        return False
    if quantization in {"Q4_K_S", "Q4_K_XS"}:
        return False
    if quantization.startswith("Q4"):
        return quantization in {"Q4_K_M", "Q4_K_L"}
    return True


def variant_passes_tag_filter(variant):
    tag_name = extract_tag_name(variant["name"])
    if not tag_name:
        return True

    lowered_tag_name = tag_name.casefold()
    if lowered_tag_name == "latest":
        return True
    if lowered_tag_name.startswith("cloud"):
        return False

    size_match = re.match(r"(\d+(?:\.\d+)?)b(?:$|[^a-z0-9])", lowered_tag_name)
    if size_match is not None:
        size_value = float(size_match.group(1))
        if size_value < 7 or size_value > 80:
            return False

    return is_allowed_quantization(tag_name)


def build_index_entry(
    model_name,
    model_url,
    description,
    badges,
    sizes,
    downloads,
    tag_count,
    updated,
    preferred_order,
):
    model_entry = {
        "name": model_name,
        "model_url": model_url,
        "tags_url": f"{model_url.rstrip('/')}/tags",
        "description": description,
        "badges": badges,
        "sizes": sizes,
        "downloads": downloads,
        "tag_count": tag_count,
        "updated": updated,
        "preferred_index": preferred_order.get(model_name, len(preferred_order)),
    }
    model_entry["display"] = build_model_display(model_entry)
    return model_entry


def parse_index_entries_from_soup(
    soup, page_url, preferred_order, seen_names=None, allow_empty=False
):
    repo_container = soup.find("div", attrs={"x-test-repos": True}) or soup.find(id="repo")
    item_nodes = (
        repo_container.select("li[x-test-model]")
        if repo_container is not None
        else soup.select("li[x-test-model]")
    )
    if not item_nodes:
        if allow_empty:
            return []
        raise RuntimeError(f"Could not parse the model listing page: {page_url}")

    model_entries = []
    if seen_names is None:
        seen_names = set()

    for item in item_nodes:
        title_container = item.find(attrs={"x-test-model-title": True}) or item.find(
            "div", title=True
        )
        title_element = title_container or item.find(
            attrs={"x-test-search-response-title": True}
        )
        if title_element is None and title_container is None:
            continue

        model_name = clean_text(
            (
                title_container.get("title")
                if title_container is not None
                else None
            )
            or title_element.get_text(" ", strip=True)
        )
        if not model_name or model_name in seen_names:
            continue

        link_element = item.find("a", href=True)
        model_url = (
            urljoin("https://ollama.com/", link_element["href"])
            if link_element is not None
            else f"{page_url.rstrip('/')}/{model_name}"
        )
        chip_container = item.find(
            "div", class_=lambda value: class_list_contains(value, "flex", "flex-wrap")
        )
        badges, sizes = extract_badges_and_sizes(chip_container, model_name)
        description_element = (
            title_container.find("p") if title_container is not None else None
        )
        downloads_element = item.find(attrs={"x-test-pull-count": True})
        tags_element = item.find(attrs={"x-test-tag-count": True})
        updated_element = item.find(attrs={"x-test-updated": True})

        model_entry = build_index_entry(
            model_name=model_name,
            model_url=model_url,
            description=clean_text(
                description_element.get_text(" ", strip=True)
                if description_element is not None
                else ""
            ),
            badges=badges,
            sizes=sizes,
            downloads=clean_text(
                downloads_element.get_text(" ", strip=True)
                if downloads_element is not None
                else ""
            ),
            tag_count=parse_integer(
                tags_element.get_text(" ", strip=True) if tags_element is not None else ""
            ),
            updated=clean_text(
                updated_element.get_text(" ", strip=True)
                if updated_element is not None
                else ""
            ),
            preferred_order=preferred_order,
        )
        model_entries.append(model_entry)
        seen_names.add(model_name)

    return model_entries


def parse_library_index_page(preferred_order, seen_names=None):
    soup = get_soup(LIBRARY_URL)
    model_entries = parse_index_entries_from_soup(
        soup, LIBRARY_URL, preferred_order, seen_names=seen_names
    )
    if not model_entries:
        raise RuntimeError("No Ollama library models were found.")

    return model_entries


def parse_search_query_pages(query, preferred_order, seen_names=None):
    search_entries = []
    if seen_names is None:
        seen_names = set()

    for page_number in range(1, MAX_SEARCH_PAGES + 1):
        if page_number == 1:
            page_url = f"{SEARCH_URL}?q={query}"
        else:
            page_url = f"{SEARCH_URL}?page={page_number}&q={query}"

        soup = get_soup(page_url)
        page_entries = parse_index_entries_from_soup(
            soup,
            page_url,
            preferred_order,
            seen_names=seen_names,
            allow_empty=True,
        )
        if not page_entries:
            break
        search_entries.extend(page_entries)

    return search_entries


def parse_model_detail_page(model_name, model_url):
    soup = get_soup(model_url)
    chip_container = soup.find(
        "div", class_=lambda value: class_list_contains(value, "flex", "flex-wrap")
    )
    badges, sizes = extract_badges_and_sizes(chip_container, model_name)
    downloads_element = soup.find(attrs={"x-test-pull-count": True})
    updated_element = soup.find(attrs={"x-test-updated": True})
    name_element = soup.find(attrs={"x-test-model-name": True})

    return {
        "name": clean_text(
            name_element.get_text(" ", strip=True) if name_element is not None else model_name
        ),
        "description": extract_summary_text(soup),
        "badges": badges,
        "sizes": sizes,
        "downloads": clean_text(
            downloads_element.get_text(" ", strip=True)
            if downloads_element is not None
            else ""
        ),
        "updated": clean_text(
            updated_element.get_text(" ", strip=True)
            if updated_element is not None
            else ""
        ),
        "tag_count": extract_page_model_count(soup),
        "model_url": model_url,
    }


def extract_updated_from_footer(footer_text, digest):
    cleaned_footer = clean_text(footer_text)
    if digest:
        cleaned_footer = cleaned_footer.replace(digest, "", 1).strip()
    cleaned_footer = re.sub(r"^[^0-9A-Za-z]+", "", cleaned_footer)
    return cleaned_footer


def parse_tag_row(row):
    desktop_container = row.find(
        "div", class_=lambda value: class_list_contains(value, "hidden", "md:flex")
    )
    if desktop_container is None:
        return None

    grid_container = desktop_container.find(
        "div",
        class_=lambda value: class_list_contains(
            value, "grid", "grid-cols-12", "items-center"
        ),
    )
    if grid_container is None:
        return None

    link_element = grid_container.find("a", href=True)
    if link_element is None:
        return None

    grid_paragraphs = grid_container.find_all("p")
    size_text = (
        clean_text(grid_paragraphs[0].get_text(" ", strip=True))
        if len(grid_paragraphs) >= 1
        else ""
    )
    context_text = (
        clean_text(grid_paragraphs[1].get_text(" ", strip=True))
        if len(grid_paragraphs) >= 2
        else ""
    )

    input_text = ""
    for div in grid_container.find_all("div", recursive=False):
        if class_list_contains(div.get("class"), "col-span-2"):
            input_text = clean_text(div.get_text(" ", strip=True))
            if input_text:
                break

    footer_element = desktop_container.find(
        "div", class_=lambda value: class_list_contains(value, "flex", "text-xs")
    )
    digest_element = (
        footer_element.find(
            "span", class_=lambda value: class_list_contains(value, "font-mono")
        )
        if footer_element is not None
        else None
    )
    digest = clean_text(
        digest_element.get_text(" ", strip=True) if digest_element is not None else ""
    )
    updated = extract_updated_from_footer(
        footer_element.get_text(" ", strip=True) if footer_element is not None else "",
        digest,
    )
    grid_text = clean_text(grid_container.get_text(" ", strip=True))

    return {
        "name": clean_text(link_element.get_text(" ", strip=True)),
        "url": urljoin(f"{LIBRARY_URL}/", link_element["href"]),
        "size": size_text,
        "context": context_text,
        "input": input_text,
        "digest": digest,
        "updated": updated,
        "is_latest": bool(re.search(r"\blatest\b", grid_text, re.I)),
    }


def parse_model_tags_page(model_name, tags_url):
    soup = get_soup(tags_url)
    chip_container = soup.find(
        "div", class_=lambda value: class_list_contains(value, "flex", "flex-wrap")
    )
    badges, sizes = extract_badges_and_sizes(chip_container, model_name)
    downloads_element = soup.find(attrs={"x-test-pull-count": True})
    updated_element = soup.find(attrs={"x-test-updated": True})

    tag_variants = []
    seen_variant_names = set()
    for row in soup.find_all("div", class_="group px-4 py-3"):
        tag_variant = parse_tag_row(row)
        if tag_variant is None or tag_variant["name"] in seen_variant_names:
            continue
        tag_variants.append(tag_variant)
        seen_variant_names.add(tag_variant["name"])

    return {
        "name": model_name,
        "description": extract_summary_text(soup),
        "badges": badges,
        "sizes": sizes,
        "downloads": clean_text(
            downloads_element.get_text(" ", strip=True)
            if downloads_element is not None
            else ""
        ),
        "updated": clean_text(
            updated_element.get_text(" ", strip=True)
            if updated_element is not None
            else ""
        ),
        "tag_count": extract_page_model_count(soup) or len(tag_variants),
        "variants": tag_variants,
        "tags_url": tags_url,
    }


def merge_model_data(index_entry, detail_entry, tags_entry, errors):
    model_name = first_nonempty(
        detail_entry.get("name"),
        tags_entry.get("name"),
        index_entry["name"],
    )
    model_entry = {
        "name": model_name,
        "model_url": first_nonempty(
            detail_entry.get("model_url"),
            index_entry["model_url"],
        ),
        "tags_url": first_nonempty(tags_entry.get("tags_url"), index_entry["tags_url"]),
        "description": first_nonempty(
            detail_entry.get("description"),
            tags_entry.get("description"),
            index_entry["description"],
        ),
        "badges": normalize_model_badges(
            model_name,
            unique_values(
                index_entry.get("badges"),
                detail_entry.get("badges"),
                tags_entry.get("badges"),
            ),
        ),
        "sizes": unique_values(
            index_entry.get("sizes"),
            detail_entry.get("sizes"),
            tags_entry.get("sizes"),
        ),
        "downloads": first_nonempty(
            tags_entry.get("downloads"),
            detail_entry.get("downloads"),
            index_entry["downloads"],
        ),
        "tag_count": tags_entry.get("tag_count")
        or detail_entry.get("tag_count")
        or index_entry["tag_count"],
        "updated": first_nonempty(
            tags_entry.get("updated"),
            detail_entry.get("updated"),
            index_entry["updated"],
        ),
        "variants": tuple(tags_entry.get("variants") or ()),
        "errors": tuple(errors),
        "preferred_index": index_entry["preferred_index"],
    }
    model_entry["display"] = build_model_display(model_entry)
    return model_entry


def load_single_model(index_entry):
    errors = []
    detail_entry = {}
    tags_entry = {}

    try:
        detail_entry = parse_model_detail_page(
            index_entry["name"], index_entry["model_url"]
        )
    except Exception as exc:
        errors.append(f"Model page failed: {exc}")
        log_message(
            f"Failed to load model page for {index_entry['name']}\n"
            f"{traceback.format_exc()}"
        )

    try:
        tags_entry = parse_model_tags_page(index_entry["name"], index_entry["tags_url"])
    except Exception as exc:
        errors.append(f"Tags page failed: {exc}")
        log_message(
            f"Failed to load tags page for {index_entry['name']}\n"
            f"{traceback.format_exc()}"
        )

    return merge_model_data(index_entry, detail_entry, tags_entry, errors)


def load_model_entries(model_entries, progress_callback=None, progress_label="models"):
    model_count = len(model_entries)
    if model_count == 0:
        if progress_callback is not None:
            progress_callback(f"No {progress_label} were found.")
        return []

    if progress_callback is not None:
        progress_callback(
            f"Found {model_count} unique {progress_label} on ollama.com. Fetching model and tags pages..."
        )

    merged_models = []
    partial_models = 0
    with ThreadPoolExecutor(max_workers=MAX_FETCH_WORKERS) as executor:
        future_map = {
            executor.submit(load_single_model, index_entry): index_entry
            for index_entry in model_entries
        }
        for completed_count, future in enumerate(as_completed(future_map), start=1):
            index_entry = future_map[future]
            try:
                model_entry = future.result()
            except Exception as exc:
                partial_models += 1
                log_message(
                    f"Unexpected failure while loading {index_entry['name']}\n"
                    f"{traceback.format_exc()}"
                )
                model_entry = merge_model_data(
                    index_entry,
                    {},
                    {},
                    [f"Unexpected loader failure: {exc}"],
                )
                merged_models.append(model_entry)
                if progress_callback is not None and (
                    completed_count == 1
                    or completed_count == model_count
                    or completed_count % 5 == 0
                ):
                    status_message = f"Loaded {completed_count}/{model_count} {progress_label}"
                    status_message += f" ({partial_models} partial)"
                    progress_callback(f"{status_message}...")
                continue

            if model_entry["errors"]:
                partial_models += 1
            merged_models.append(model_entry)

            if progress_callback is not None and (
                completed_count == 1
                or completed_count == model_count
                or completed_count % 5 == 0
            ):
                status_message = f"Loaded {completed_count}/{model_count} {progress_label}"
                if partial_models:
                    status_message += f" ({partial_models} partial)"
                progress_callback(f"{status_message}...")

    return merged_models


def load_library_models(progress_callback=None):
    preferred_order = {
        model_name: index for index, model_name in enumerate(PREFERRED_MODELS)
    }
    seen_names = set()

    if progress_callback is not None:
        progress_callback("Loading Ollama library index...")

    model_entries = parse_library_index_page(preferred_order, seen_names=seen_names)
    if progress_callback is not None:
        progress_callback(
            f"Loaded {len(model_entries)} models from the Ollama library index."
        )

    merged_models = load_model_entries(
        model_entries,
        progress_callback=progress_callback,
        progress_label="library models",
    )
    merged_models = sort_models_by_category(merged_models)
    write_models_text(merged_models)
    return merged_models


def load_search_models(existing_names=None, progress_callback=None):
    preferred_order = {
        model_name: index for index, model_name in enumerate(PREFERRED_MODELS)
    }
    seen_names = set(existing_names or ())
    model_entries = []

    for query in SEARCH_QUERIES:
        if progress_callback is not None:
            progress_callback(f'Loading Ollama search results for "{query}"...')

        query_entries = parse_search_query_pages(
            query, preferred_order, seen_names=seen_names
        )
        model_entries.extend(query_entries)

        if progress_callback is not None:
            progress_callback(
                f'Added {len(query_entries)} models from search query "{query}".'
            )

    merged_models = load_model_entries(
        model_entries,
        progress_callback=progress_callback,
        progress_label="search models",
    )
    merged_models = sort_models_by_category(merged_models)
    return merged_models


def sort_models_by_name(model_entries):
    return sorted(model_entries, key=lambda model: model["name"].casefold())


def sort_models_by_downloads(model_entries):
    return sorted(
        model_entries,
        key=lambda model: (-parse_human_number(model["downloads"]), model["name"].casefold()),
    )


def sort_models_by_tag_count(model_entries):
    return sorted(
        model_entries,
        key=lambda model: (-model["tag_count"], model["name"].casefold()),
    )


def sort_models_by_category(model_entries):
    def category_key(model_entry):
        model_badges = set(model_entry["badges"])
        return (
            0 if model_entry["name"] in PREFERRED_MODELS else 1,
            model_entry.get("preferred_index", 0),
            0 if "tools" in model_badges else 1,
            0 if "thinking" in model_badges else 1,
            model_entry["name"].casefold(),
        )

    return sorted(model_entries, key=category_key)


def sort_model_entries(model_entries, sort_kind):
    if sort_kind == "name":
        return sort_models_by_name(model_entries)
    if sort_kind == "downloads":
        return sort_models_by_downloads(model_entries)
    if sort_kind == "tags":
        return sort_models_by_tag_count(model_entries)
    return sort_models_by_category(model_entries)


def write_models_text(model_entries):
    output_path = Path.cwd() / TEXT_OUTPUT_FILENAME
    output_text = "\n".join(model_entry["display"] for model_entry in model_entries)
    if output_text:
        output_text += "\n"

    output_path.write_text(output_text, encoding="utf-8")
    log_message(f"Wrote library model list: {output_path}")


def build_variant_display_parts(variant):
    display_parts = []
    if variant["size"]:
        display_parts.append(variant["size"])
    if variant["context"]:
        display_parts.append(f"{variant['context']} context")
    if variant["input"]:
        display_parts.append(variant["input"])
    if variant["digest"]:
        display_parts.append(variant["digest"])
    if variant["updated"]:
        display_parts.append(variant["updated"])
    return display_parts


def show_models_window():
    isolate_tk_environment()

    import tkinter as tk
    from tkinter import messagebox

    class DarkVerticalScrollbar(tk.Canvas):
        def __init__(self, master, **kwargs):
            super().__init__(
                master,
                bg=DARK_ANTHRACITE_PANEL,
                bd=0,
                highlightthickness=0,
                relief="flat",
                width=16,
                **kwargs,
            )
            self._command = None
            self._first = 0.0
            self._last = 1.0
            self._drag_offset = 0
            self._thumb_id = self.create_rectangle(
                3,
                2,
                13,
                30,
                fill=DARK_BUTTON_ACTIVE,
                outline=DARK_BUTTON_ACTIVE,
            )
            self.bind("<Configure>", lambda event: self._draw_thumb())
            self.bind("<Button-1>", self._on_click)
            self.bind("<B1-Motion>", self._on_drag)
            self.bind("<ButtonRelease-1>", self._on_release)

        def configure(self, cnf=None, **kwargs):
            if cnf and isinstance(cnf, dict):
                kwargs.update(cnf)
                cnf = None

            command = kwargs.pop("command", None)
            if command is not None:
                self._command = command

            if kwargs:
                return super().configure(cnf, **kwargs)

            return None

        config = configure

        def set(self, first, last):
            self._first = max(0.0, min(float(first), 1.0))
            self._last = max(self._first, min(float(last), 1.0))
            self._draw_thumb()

        def _thumb_bounds(self):
            height = max(self.winfo_height(), 1)
            if self._last >= 1.0 and self._first <= 0.0:
                return 2, height - 2

            thumb_height = max(int((self._last - self._first) * height), 28)
            available_height = max(height - thumb_height - 4, 1)
            top = int(2 + self._first * available_height)
            bottom = min(top + thumb_height, height - 2)
            return top, bottom

        def _draw_thumb(self):
            top, bottom = self._thumb_bounds()
            self.coords(self._thumb_id, 3, top, 13, bottom)
            self.itemconfig(
                self._thumb_id,
                fill=DARK_BUTTON_ACTIVE,
                outline=DARK_BUTTON_ACTIVE,
            )

        def _scroll_to_pointer(self, pointer_y):
            if self._command is None:
                return

            height = max(self.winfo_height(), 1)
            top, bottom = self._thumb_bounds()
            thumb_height = bottom - top
            available_height = max(height - thumb_height - 4, 1)
            fraction = (pointer_y - self._drag_offset - 2) / available_height
            self._command("moveto", max(0.0, min(fraction, 1.0)))

        def _on_click(self, event):
            top, bottom = self._thumb_bounds()
            if top <= event.y <= bottom:
                self._drag_offset = event.y - top
            else:
                self._drag_offset = max((bottom - top) // 2, 0)
                self._scroll_to_pointer(event.y)

            return "break"

        def _on_drag(self, event):
            self._scroll_to_pointer(event.y)
            return "break"

        def _on_release(self, event):
            self._drag_offset = 0
            return "break"

    root = tk.Tk()
    root.title(APP_NAME)
    root.configure(bg=DARK_ANTHRACITE_BLUE)
    root.resizable(True, True)

    result_queue = queue.Queue()
    message_var = tk.StringVar(value="Scanning Ollama library...")
    detail_title_var = tk.StringVar(value="Model Details")
    tags_title_var = tk.StringVar(value="Available Tags (0)")
    selected_command_var = tk.StringVar(
        value='Select a tag to install it with: ollama run "<model:tag>" ""'
    )
    all_models = []
    current_models = []
    all_variants = []
    current_variants = []
    selected_model_index = [None]
    selected_variant_index = [None]
    interface_busy = [False]
    filter_enabled = [False]
    current_sort_kind = ["category"]

    def close(event=None):
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", close)
    root.bind("<Escape>", close)
    root.bind("<F5>", lambda event: (refresh_models(), "break")[1])

    frame = tk.Frame(root, bg=DARK_ANTHRACITE_BLUE, padx=18, pady=18)
    frame.pack(fill="both", expand=True)

    header_frame = tk.Frame(frame, bg=DARK_ANTHRACITE_BLUE)
    header_frame.pack(fill="x")

    tk.Label(
        header_frame,
        textvariable=message_var,
        bg=DARK_ANTHRACITE_BLUE,
        fg=DARK_TEXT,
        justify="left",
        wraplength=720,
    ).pack(side="left", fill="x", expand=True, anchor="w")

    sort_button_frame = tk.Frame(header_frame, bg=DARK_ANTHRACITE_BLUE)
    sort_button_frame.pack(side="right")

    body_frame = tk.Frame(frame, bg=DARK_ANTHRACITE_BLUE)
    body_frame.pack(fill="both", expand=True, pady=(12, 16))
    body_frame.grid_columnconfigure(0, weight=2)
    body_frame.grid_columnconfigure(1, weight=3)
    body_frame.grid_rowconfigure(0, weight=1)

    list_frame = tk.Frame(
        body_frame,
        bg=DARK_ANTHRACITE_PANEL,
        highlightthickness=1,
        highlightbackground=DARK_ANTHRACITE_BORDER,
        highlightcolor=DARK_ANTHRACITE_BORDER,
    )
    list_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

    detail_frame = tk.Frame(
        body_frame,
        bg=DARK_ANTHRACITE_PANEL,
        highlightthickness=1,
        highlightbackground=DARK_ANTHRACITE_BORDER,
        highlightcolor=DARK_ANTHRACITE_BORDER,
    )
    detail_frame.grid(row=0, column=1, sticky="nsew")

    list_scrollbar = DarkVerticalScrollbar(list_frame)
    list_scrollbar.pack(side="right", fill="y")

    model_text = tk.Text(
        list_frame,
        bg=DARK_ANTHRACITE_PANEL,
        fg=DARK_TEXT,
        highlightthickness=0,
        relief="flat",
        font=("Consolas", 10),
        width=48,
        wrap="none",
        cursor="arrow",
        padx=8,
        pady=8,
        spacing1=1,
        spacing3=3,
        yscrollcommand=list_scrollbar.set,
    )
    model_text.pack(side="left", fill="both", expand=True)
    list_scrollbar.config(command=model_text.yview)

    detail_header = tk.Label(
        detail_frame,
        textvariable=detail_title_var,
        bg=DARK_ANTHRACITE_PANEL,
        fg=DARK_TEXT,
        anchor="w",
        justify="left",
        font=("Segoe UI", 10, "bold"),
        padx=10,
        pady=10,
    )
    detail_header.pack(fill="x")

    detail_body_frame = tk.Frame(detail_frame, bg=DARK_ANTHRACITE_PANEL)
    detail_body_frame.pack(fill="both", expand=True, padx=0, pady=0)
    detail_body_frame.grid_columnconfigure(0, weight=1)
    detail_body_frame.grid_rowconfigure(0, weight=2)
    detail_body_frame.grid_rowconfigure(1, weight=1)

    detail_text_frame = tk.Frame(detail_body_frame, bg=DARK_ANTHRACITE_PANEL)
    detail_text_frame.grid(row=0, column=0, sticky="nsew")

    detail_scrollbar = DarkVerticalScrollbar(detail_text_frame)
    detail_scrollbar.pack(side="right", fill="y")

    details_text = tk.Text(
        detail_text_frame,
        bg=DARK_ANTHRACITE_PANEL,
        fg=DARK_TEXT,
        highlightthickness=0,
        relief="flat",
        font=("Consolas", 10),
        wrap="word",
        cursor="arrow",
        padx=10,
        pady=10,
        spacing1=1,
        spacing3=4,
        yscrollcommand=detail_scrollbar.set,
    )
    details_text.pack(side="left", fill="both", expand=True)
    detail_scrollbar.config(command=details_text.yview)

    tags_frame = tk.Frame(
        detail_body_frame,
        bg=DARK_ANTHRACITE_PANEL,
        highlightthickness=1,
        highlightbackground=DARK_ANTHRACITE_BORDER,
        highlightcolor=DARK_ANTHRACITE_BORDER,
    )
    tags_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))

    tk.Label(
        tags_frame,
        textvariable=tags_title_var,
        bg=DARK_ANTHRACITE_PANEL,
        fg=DARK_TEXT,
        anchor="w",
        justify="left",
        font=("Segoe UI", 10, "bold"),
        padx=10,
        pady=8,
    ).pack(fill="x")

    tags_list_frame = tk.Frame(tags_frame, bg=DARK_ANTHRACITE_PANEL)
    tags_list_frame.pack(fill="both", expand=True, padx=0, pady=0)

    tags_scrollbar = DarkVerticalScrollbar(tags_list_frame)
    tags_scrollbar.pack(side="right", fill="y")

    tags_listbox = tk.Listbox(
        tags_list_frame,
        bg=DARK_ANTHRACITE_PANEL,
        fg=DARK_TEXT,
        selectbackground="#2f3c49",
        selectforeground=DARK_TEXT,
        activestyle="none",
        highlightthickness=0,
        relief="flat",
        bd=0,
        exportselection=False,
        font=("Consolas", 10),
    )
    tags_listbox.pack(side="left", fill="both", expand=True, padx=10, pady=(0, 8))
    tags_scrollbar.config(command=tags_listbox.yview)
    tags_listbox.config(yscrollcommand=tags_scrollbar.set)

    tk.Label(
        tags_frame,
        textvariable=selected_command_var,
        bg=DARK_ANTHRACITE_PANEL,
        fg=DARK_MUTED_TEXT,
        anchor="w",
        justify="left",
        wraplength=640,
        padx=10,
        pady=8,
    ).pack(fill="x")

    model_text.tag_configure("model_name", foreground=DARK_TEXT)
    model_text.tag_configure("model_meta", foreground=DARK_MUTED_TEXT)
    model_text.tag_configure("selected", background="#2f3c49")
    details_text.tag_configure("detail_heading", foreground=DARK_TEXT)
    details_text.tag_configure("detail_label", foreground=DARK_TEXT)
    details_text.tag_configure("detail_value", foreground=DARK_MUTED_TEXT)
    details_text.tag_configure("detail_code", foreground=DARK_TEXT)
    details_text.tag_configure("detail_muted", foreground=DARK_MUTED_TEXT)
    details_text.tag_configure("detail_error", foreground="#ff9696")
    for badge_name, style in BADGE_STYLES.items():
        model_text.tag_configure(
            f"badge_{badge_name}",
            background=style["background"],
            foreground=style["foreground"],
        )
        model_text.tag_raise(f"badge_{badge_name}", "selected")

    model_text.insert("end", "Scanning Ollama library...")
    model_text.config(state="disabled")
    details_text.insert(
        "end",
        "Select a model to see its description, categories, and tag list.",
        ("detail_muted",),
    )
    details_text.config(state="disabled")
    tags_listbox.insert("end", "No tags loaded.")
    tags_listbox.config(state="disabled")

    button_frame = tk.Frame(frame, bg=DARK_ANTHRACITE_BLUE)
    button_frame.pack(fill="x")

    refresh_button = tk.Button(
        button_frame,
        text="Refresh Library",
        command=lambda: refresh_models(),
        bg=DARK_BUTTON,
        fg=DARK_TEXT,
        activebackground=DARK_BUTTON_ACTIVE,
        activeforeground=DARK_TEXT,
        relief="flat",
        bd=0,
        padx=14,
        pady=6,
        state="disabled",
    )
    refresh_button.pack(side="left")

    main_library_button = tk.Button(
        sort_button_frame,
        text="Main Library",
        command=lambda: refresh_models(),
        bg=DARK_BUTTON,
        fg=DARK_TEXT,
        activebackground=DARK_BUTTON_ACTIVE,
        activeforeground=DARK_TEXT,
        relief="flat",
        bd=0,
        padx=14,
        pady=6,
        state="disabled",
    )
    main_library_button.pack(side="left", padx=(0, 8))

    filter_button = tk.Button(
        sort_button_frame,
        text="Filter",
        command=lambda: toggle_variant_filter(),
        bg=DARK_BUTTON,
        fg=DARK_TEXT,
        activebackground=DARK_BUTTON_ACTIVE,
        activeforeground=DARK_TEXT,
        relief="flat",
        bd=0,
        padx=14,
        pady=6,
        state="disabled",
    )
    filter_button.pack(side="left", padx=(0, 8))

    sort_name_button = tk.Button(
        sort_button_frame,
        text="Sort by Name",
        command=lambda: sort_current_models("name"),
        bg=DARK_BUTTON,
        fg=DARK_TEXT,
        activebackground=DARK_BUTTON_ACTIVE,
        activeforeground=DARK_TEXT,
        relief="flat",
        bd=0,
        padx=14,
        pady=6,
        state="disabled",
    )
    sort_name_button.pack(side="left", padx=(0, 8))

    sort_tags_button = tk.Button(
        sort_button_frame,
        text="Sort by Tags",
        command=lambda: sort_current_models("tags"),
        bg=DARK_BUTTON,
        fg=DARK_TEXT,
        activebackground=DARK_BUTTON_ACTIVE,
        activeforeground=DARK_TEXT,
        relief="flat",
        bd=0,
        padx=14,
        pady=6,
        state="disabled",
    )
    sort_tags_button.pack(side="left", padx=(8, 0))

    sort_category_button = tk.Button(
        sort_button_frame,
        text="Sort by Category",
        command=lambda: sort_current_models("category"),
        bg=DARK_BUTTON,
        fg=DARK_TEXT,
        activebackground=DARK_BUTTON_ACTIVE,
        activeforeground=DARK_TEXT,
        relief="flat",
        bd=0,
        padx=14,
        pady=6,
        state="disabled",
    )
    sort_category_button.pack(side="left", padx=(8, 0))

    install_button = tk.Button(
        button_frame,
        text="Install Selected LLM",
        command=lambda: install_selected_variant(),
        bg=BRIGHT_SUCCESS,
        fg="#ffffff",
        activebackground=BRIGHT_SUCCESS_ACTIVE,
        activeforeground="#ffffff",
        relief="flat",
        bd=0,
        padx=18,
        pady=6,
        state="disabled",
    )
    install_button.pack(side="right", padx=(0, 10))

    tk.Button(
        button_frame,
        text="Close",
        command=close,
        bg=DARK_BUTTON,
        fg=DARK_TEXT,
        activebackground=DARK_BUTTON_ACTIVE,
        activeforeground=DARK_TEXT,
        relief="flat",
        bd=0,
        padx=18,
        pady=6,
    ).pack(side="right")

    root.update_idletasks()
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    position_x = (screen_width - WINDOW_WIDTH) // 2
    position_y = (screen_height - WINDOW_HEIGHT) // 2
    root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}+{position_x}+{position_y}")
    try:
        if os.name == "nt":
            root.state("zoomed")
        else:
            root.attributes("-zoomed", True)
    except Exception:
        pass
    schedule_dark_title_bar(root)
    model_text.focus_set()

    def set_model_text_state(state):
        model_text.config(state=state)

    def set_details_text_state(state):
        details_text.config(state=state)

    def clear_model_text():
        set_model_text_state("normal")
        model_text.delete("1.0", "end")

    def clear_details_text():
        set_details_text_state("normal")
        details_text.delete("1.0", "end")

    def clear_variant_list():
        all_variants[:] = []
        current_variants[:] = []
        selected_variant_index[0] = None
        tags_title_var.set("Available Tags (0)")
        tags_listbox.config(state="normal")
        tags_listbox.delete(0, "end")
        tags_listbox.insert("end", "No tags loaded.")
        tags_listbox.config(state="disabled")
        selected_command_var.set(
            'Select a tag to install it with: ollama run "<model:tag>" ""'
        )

    def update_filter_button_state():
        filter_button.config(
            bg=DARK_BUTTON_ACTIVE if filter_enabled[0] else DARK_BUTTON,
            activebackground=DARK_BUTTON_ACTIVE,
        )

    def apply_variant_filter(variants):
        if not filter_enabled[0]:
            return list(variants)
        return [variant for variant in variants if variant_passes_tag_filter(variant)]

    def model_passes_filter(model_entry):
        if not filter_enabled[0]:
            return True
        if not model_entry["variants"]:
            return True
        return any(variant_passes_tag_filter(variant) for variant in model_entry["variants"])

    def apply_model_filter(model_entries):
        if not filter_enabled[0]:
            return list(model_entries)
        return [model_entry for model_entry in model_entries if model_passes_filter(model_entry)]

    def finish_model_text_update():
        set_model_text_state("disabled")

    def finish_details_text_update():
        set_details_text_state("disabled")

    def insert_model_entry(model_entry):
        model_text.insert("end", model_entry["name"], ("model_name",))
        if model_entry["downloads"]:
            model_text.insert(
                "end",
                f"  [{model_entry['downloads']} pulls]",
                ("model_meta",),
            )
        if model_entry["tag_count"]:
            model_text.insert(
                "end",
                f"  [{model_entry['tag_count']} tags]",
                ("model_meta",),
            )

        for badge_name in model_entry["badges"]:
            model_text.insert("end", "  ")
            model_text.insert("end", f" {badge_name} ", (f"badge_{badge_name}",))

        model_text.insert("end", "\n")

    def write_detail_field(label, value, value_tag="detail_value"):
        details_text.insert("end", f"{label}: ", ("detail_label",))
        details_text.insert("end", f"{value}\n", (value_tag,))

    def format_variant_entry(variant):
        display_text = variant["name"]
        variant_display_parts = build_variant_display_parts(variant)
        if variant_display_parts:
            display_text += "  " + "  ".join(f"[{part}]" for part in variant_display_parts)
        return display_text

    def get_selected_variant():
        selected_index = selected_variant_index[0]
        if selected_index is None:
            return None
        if selected_index < 0 or selected_index >= len(current_variants):
            return None
        return current_variants[selected_index]

    def update_selected_command_label():
        selected_variant = get_selected_variant()
        if selected_variant is None:
            selected_command_var.set(
                'Select a tag to install it with: ollama run "<model:tag>" ""'
            )
            return

        selected_command_var.set(
            f'Install command: ollama run "{selected_variant["name"]}" ""'
        )

    def update_install_button_state():
        install_button.config(
            state="normal"
            if not interface_busy[0] and get_selected_variant() is not None
            else "disabled"
        )

    def select_variant(index):
        tags_listbox.selection_clear(0, "end")
        selected_variant_index[0] = None
        if index is None or index < 0 or index >= len(current_variants):
            update_selected_command_label()
            update_install_button_state()
            return

        selected_variant_index[0] = index
        tags_listbox.selection_set(index)
        tags_listbox.activate(index)
        tags_listbox.see(index)
        update_selected_command_label()
        update_install_button_state()

    def populate_variant_list(variants, selected_variant_name=None):
        current_variants[:] = list(variants)
        selected_variant_index[0] = None
        if filter_enabled[0]:
            tags_title_var.set(
                f"Available Tags ({len(current_variants)} of {len(all_variants)})"
            )
        else:
            tags_title_var.set(f"Available Tags ({len(current_variants)})")
        tags_listbox.config(state="normal")
        tags_listbox.delete(0, "end")

        if current_variants:
            for variant in current_variants:
                tags_listbox.insert("end", format_variant_entry(variant))
            if selected_variant_name:
                for index, variant in enumerate(current_variants):
                    if variant["name"] == selected_variant_name:
                        select_variant(index)
                        break
                else:
                    select_variant(0)
            else:
                select_variant(0)
        else:
            if all_variants and filter_enabled[0]:
                tags_listbox.insert("end", "No tags match the current filter.")
            else:
                tags_listbox.insert("end", "No tag rows were parsed from the tags page.")
            tags_listbox.config(state="disabled")
            update_selected_command_label()
            update_install_button_state()

    def refresh_variant_list(selected_variant_name=None):
        filtered_variants = apply_variant_filter(all_variants)
        populate_variant_list(filtered_variants, selected_variant_name=selected_variant_name)

    def toggle_variant_filter():
        if interface_busy[0] or not all_models:
            return

        selected_name = None
        if selected_model_index[0] is not None and selected_model_index[0] < len(current_models):
            selected_name = current_models[selected_model_index[0]]["name"]

        filter_enabled[0] = not filter_enabled[0]
        update_filter_button_state()
        refresh_model_list(selected_name=selected_name)
        message_var.set(
            "Model and tag filter enabled."
            if filter_enabled[0]
            else "Model and tag filter disabled."
        )

    def handle_variant_selection(event=None):
        if interface_busy[0]:
            return "break"

        selection = tags_listbox.curselection()
        if selection:
            select_variant(selection[0])
        else:
            select_variant(None)
        return "break"

    def render_model_details(model_entry):
        clear_details_text()
        if model_entry is None:
            detail_title_var.set("Model Details")
            clear_variant_list()
            details_text.insert(
                "end",
                "Select a model to see its description, categories, and tag list.",
                ("detail_muted",),
            )
            finish_details_text_update()
            return

        detail_title_var.set(model_entry["name"])
        write_detail_field("Model", model_entry["name"], "detail_code")
        write_detail_field(
            "Categories",
            ", ".join(model_entry["badges"]) if model_entry["badges"] else "None",
        )
        write_detail_field(
            "Sizes",
            ", ".join(model_entry["sizes"]) if model_entry["sizes"] else "None",
        )
        write_detail_field("Downloads", model_entry["downloads"] or "Unknown")
        write_detail_field("Tags", str(model_entry["tag_count"] or len(model_entry["variants"])))
        write_detail_field("Updated", model_entry["updated"] or "Unknown")
        write_detail_field(
            "Install",
            'Select a tag on the right, then click "Install Selected LLM".',
        )
        write_detail_field("Model Page", model_entry["model_url"] or "Unknown")
        write_detail_field("Tags Page", model_entry["tags_url"] or "Unknown")

        details_text.insert("end", "\nDescription\n", ("detail_heading",))
        details_text.insert(
            "end",
            f"{model_entry['description'] or 'No description available.'}\n",
            ("detail_value",),
        )

        if model_entry["errors"]:
            details_text.insert("end", "\nPartial Fetch Errors\n", ("detail_heading",))
            for error_text in model_entry["errors"]:
                details_text.insert("end", f"{error_text}\n", ("detail_error",))

        finish_details_text_update()
        details_text.see("1.0")
        all_variants[:] = list(model_entry["variants"])
        refresh_variant_list()

    def select_model(index):
        model_text.tag_remove("selected", "1.0", "end")
        selected_model_index[0] = None
        if index is None or index < 0 or index >= len(current_models):
            render_model_details(None)
            return "break"

        selected_model_index[0] = index
        line_start = f"{index + 1}.0"
        line_end = f"{index + 1}.end"
        model_text.tag_add("selected", line_start, line_end)
        model_text.mark_set("insert", line_start)
        model_text.see(line_start)
        render_model_details(current_models[index])
        return "break"

    def select_model_by_name(model_name):
        for index, model_entry in enumerate(current_models):
            if model_entry["name"] == model_name:
                return select_model(index)
        if current_models:
            return select_model(0)
        return select_model(None)

    def get_model_index_at_event(event):
        text_index = model_text.index(f"@{event.x},{event.y}")
        line_number = int(text_index.split(".", maxsplit=1)[0])
        model_index = line_number - 1
        if 0 <= model_index < len(current_models):
            return model_index

        return None

    def select_clicked_model(event):
        if interface_busy[0]:
            return "break"
        model_text.focus_set()
        return select_model(get_model_index_at_event(event))

    def move_selected_model(offset):
        if interface_busy[0]:
            return "break"
        if not current_models:
            return "break"

        current_index = selected_model_index[0]
        if current_index is None:
            current_index = 0
        else:
            current_index = min(
                max(current_index + offset, 0),
                len(current_models) - 1,
            )

        return select_model(current_index)

    def select_first_model(event=None):
        if interface_busy[0]:
            return "break"
        if current_models:
            return select_model(0)
        return "break"

    def select_last_model(event=None):
        if interface_busy[0]:
            return "break"
        if current_models:
            return select_model(len(current_models) - 1)
        return "break"

    model_text.bind("<Button-1>", select_clicked_model)
    model_text.bind("<Up>", lambda event: move_selected_model(-1))
    model_text.bind("<Down>", lambda event: move_selected_model(1))
    model_text.bind("<Home>", select_first_model)
    model_text.bind("<End>", select_last_model)
    tags_listbox.bind("<<ListboxSelect>>", handle_variant_selection)
    tags_listbox.bind("<Double-Button-1>", lambda event: (install_selected_variant(), "break")[1])
    tags_listbox.bind("<Return>", lambda event: (install_selected_variant(), "break")[1])

    def populate_models(model_entries, selected_name=None):
        current_models[:] = model_entries
        selected_model_index[0] = None
        clear_model_text()

        for model_entry in model_entries:
            insert_model_entry(model_entry)

        finish_model_text_update()

        if model_entries:
            select_model_by_name(selected_name or model_entries[0]["name"])
        else:
            render_model_details(None)

    def refresh_model_list(selected_name=None):
        filtered_models = apply_model_filter(all_models)
        populate_models(filtered_models, selected_name=selected_name)

    def prepare_for_model_reload(list_message):
        selected_model_index[0] = None
        clear_model_text()
        model_text.insert("end", list_message)
        finish_model_text_update()
        render_model_details(None)

    def sort_current_models(sort_kind):
        if not all_models:
            messagebox.showwarning(APP_NAME, "No models are available to sort.")
            return

        selected_name = None
        if selected_model_index[0] is not None and selected_model_index[0] < len(current_models):
            selected_name = current_models[selected_model_index[0]]["name"]

        current_sort_kind[0] = sort_kind
        sorted_models = sort_model_entries(all_models, sort_kind)
        sort_message = f"sorted by {sort_kind}"
        all_models[:] = sorted_models
        refresh_model_list(selected_name=selected_name)
        write_models_text(current_models)
        message_var.set(f"{len(current_models)} model(s) shown, {sort_message}.")

    def apply_controls_state():
        has_models = bool(all_models)
        refresh_button.config(state="disabled" if interface_busy[0] else "normal")
        main_library_button.config(state="disabled" if interface_busy[0] else "normal")
        sort_state = "normal" if has_models and not interface_busy[0] else "disabled"
        filter_button.config(state=sort_state)
        sort_name_button.config(state=sort_state)
        sort_tags_button.config(state=sort_state)
        sort_category_button.config(state=sort_state)
        tags_listbox.config(
            state="disabled"
            if interface_busy[0] or not current_variants
            else "normal"
        )
        update_filter_button_state()
        update_install_button_state()

    def set_busy(message):
        interface_busy[0] = True
        message_var.set(message)
        apply_controls_state()

    def set_ready(message=None):
        interface_busy[0] = False
        if message:
            message_var.set(message)
        apply_controls_state()

    def scan_models():
        try:
            log_message("Starting Ollama library scan.")
            model_entries = load_library_models(
                progress_callback=lambda status: result_queue.put(("progress", status))
            )
            log_message(f"Loaded {len(model_entries)} library model(s).")
            result_queue.put(("models", model_entries))
        except Exception as exc:
            log_message(traceback.format_exc())
            result_queue.put(("error", str(exc)))

    def scan_search_models():
        try:
            log_message(
                "Starting Ollama abliterated, uncensored, and derestricted search scan."
            )
            model_entries = load_search_models(
                progress_callback=lambda status: result_queue.put(("progress", status)),
            )
            log_message(f"Loaded {len(model_entries)} search model(s).")
            result_queue.put(("search_models", model_entries))
        except Exception as exc:
            log_message(traceback.format_exc())
            result_queue.put(("error", str(exc)))

    def refresh_models():
        prepare_for_model_reload("Scanning Ollama library...")
        set_busy("Scanning Ollama library...")
        threading.Thread(target=scan_models, daemon=True).start()

    def load_abliterated_models():
        set_busy(
            'Scanning "abliterated", "uncensored", and "derestricted" search results...'
        )
        threading.Thread(
            target=scan_search_models,
            daemon=True,
        ).start()

    def install_selected_variant():
        selected_variant = get_selected_variant()
        if selected_variant is None:
            messagebox.showwarning(APP_NAME, "Select a tag to install.")
            return

        selected_tag = selected_variant["name"]
        set_busy(f'Installing {selected_tag} with ollama run "{selected_tag}" ""...')

        def install_variant():
            try:
                ollama_executable = resolve_ollama_executable()
                log_message(f"Installing Ollama model via run: {selected_tag}")
                install_ollama_model(ollama_executable, selected_tag)
                log_message(f"Installed Ollama model via run: {selected_tag}")
                result_queue.put(("installed", selected_tag))
            except Exception as exc:
                log_message(traceback.format_exc())
                result_queue.put(("install_error", str(exc)))

        threading.Thread(target=install_variant, daemon=True).start()

    def schedule_poll_results():
        if root.winfo_exists():
            root.after(100, poll_results)

    def poll_results():
        try:
            result_type, payload = result_queue.get_nowait()
        except queue.Empty:
            schedule_poll_results()
            return

        try:
            if result_type == "progress":
                message_var.set(payload)
            elif result_type == "models":
                sorted_payload = sort_model_entries(payload, current_sort_kind[0])
                all_models[:] = sorted_payload
                refresh_model_list()
                write_models_text(all_models)
                set_ready(f"{len(current_models)} model(s) found in the Ollama library.")
            elif result_type == "search_models":
                all_models[:] = sort_model_entries(payload, current_sort_kind[0])
                refresh_model_list()
                write_models_text(all_models)
                set_ready(
                    f'{len(current_models)} model(s) found in the "Abliterated" search set.'
                )
            elif result_type == "installed":
                set_ready(f"Installed {payload}.")
                messagebox.showinfo(
                    APP_NAME,
                    f'Installed Ollama model:\n\n{payload}\n\nCommand used:\nollama run "{payload}" ""',
                )
            elif result_type == "install_error":
                set_ready()
                messagebox.showerror(APP_NAME, payload)
            else:
                set_ready()
                selected_model_index[0] = None
                clear_model_text()
                model_text.insert("end", payload)
                finish_model_text_update()
                render_model_details(None)
                messagebox.showerror(APP_NAME, payload)
        finally:
            schedule_poll_results()

    refresh_models()
    root.after(100, poll_results)
    root.mainloop()


def show_error(message):
    try:
        isolate_tk_environment()

        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(APP_NAME, message)
        root.destroy()
    except Exception:
        print(f"Error: {message}", file=sys.stderr)


def main():
    try:
        log_message("Starting application.")
        show_models_window()
    except Exception as exc:
        log_message(traceback.format_exc())
        show_error(str(exc))
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
