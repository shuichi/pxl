#define UNICODE
#define _UNICODE
#define WIN32_LEAN_AND_MEAN

#include <shellapi.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <windows.h>

#define APP_NAME L"pxl"
#define APP_DISPLAY_NAME L"Pxl"
#define LOG_SUBDIR L"pxl"
#define LOG_FILE L"pxl-launcher.log"

typedef struct WideString {
    wchar_t *data;
    size_t length;
    size_t capacity;
} WideString;

static void show_error(const wchar_t *message) {
    MessageBoxW(NULL, message, APP_DISPLAY_NAME, MB_ICONERROR | MB_OK);
}

static void show_last_error(const wchar_t *prefix, DWORD error_code) {
    wchar_t *system_message = NULL;
    FormatMessageW(
        FORMAT_MESSAGE_ALLOCATE_BUFFER | FORMAT_MESSAGE_FROM_SYSTEM |
            FORMAT_MESSAGE_IGNORE_INSERTS,
        NULL,
        error_code,
        0,
        (LPWSTR)&system_message,
        0,
        NULL);

    wchar_t message[4096];
    if (system_message != NULL) {
        swprintf_s(message, 4096, L"%ls\n\n%ls", prefix, system_message);
        LocalFree(system_message);
    } else {
        swprintf_s(message, 4096, L"%ls\n\nError code: %lu", prefix, error_code);
    }

    show_error(message);
}

static bool wide_string_reserve(WideString *string, size_t additional) {
    size_t required = string->length + additional + 1;
    if (required <= string->capacity) {
        return true;
    }

    size_t next_capacity = string->capacity == 0 ? 256 : string->capacity;
    while (next_capacity < required) {
        if (next_capacity > SIZE_MAX / 2) {
            return false;
        }
        next_capacity *= 2;
    }

    wchar_t *next_data =
        (wchar_t *)realloc(string->data, next_capacity * sizeof(wchar_t));
    if (next_data == NULL) {
        return false;
    }

    string->data = next_data;
    string->capacity = next_capacity;
    return true;
}

static bool wide_string_append_char(WideString *string, wchar_t value) {
    if (!wide_string_reserve(string, 1)) {
        return false;
    }

    string->data[string->length++] = value;
    string->data[string->length] = L'\0';
    return true;
}

static bool wide_string_append(WideString *string, const wchar_t *value) {
    size_t value_length = wcslen(value);
    if (!wide_string_reserve(string, value_length)) {
        return false;
    }

    memcpy(
        string->data + string->length,
        value,
        (value_length + 1) * sizeof(wchar_t));
    string->length += value_length;
    return true;
}

static bool argument_needs_quotes(const wchar_t *argument) {
    if (argument[0] == L'\0') {
        return true;
    }

    for (const wchar_t *cursor = argument; *cursor != L'\0'; cursor++) {
        if (*cursor == L' ' || *cursor == L'\t' || *cursor == L'\n' ||
            *cursor == L'\v' || *cursor == L'"') {
            return true;
        }
    }

    return false;
}

static bool append_quoted_argument(WideString *command, const wchar_t *argument) {
    if (command->length > 0 && !wide_string_append_char(command, L' ')) {
        return false;
    }

    if (!argument_needs_quotes(argument)) {
        return wide_string_append(command, argument);
    }

    if (!wide_string_append_char(command, L'"')) {
        return false;
    }

    size_t backslash_count = 0;
    for (const wchar_t *cursor = argument; *cursor != L'\0'; cursor++) {
        if (*cursor == L'\\') {
            backslash_count++;
            continue;
        }

        if (*cursor == L'"') {
            for (size_t index = 0; index < (backslash_count * 2) + 1; index++) {
                if (!wide_string_append_char(command, L'\\')) {
                    return false;
                }
            }
            backslash_count = 0;
            if (!wide_string_append_char(command, L'"')) {
                return false;
            }
            continue;
        }

        for (size_t index = 0; index < backslash_count; index++) {
            if (!wide_string_append_char(command, L'\\')) {
                return false;
            }
        }
        backslash_count = 0;
        if (!wide_string_append_char(command, *cursor)) {
            return false;
        }
    }

    for (size_t index = 0; index < backslash_count * 2; index++) {
        if (!wide_string_append_char(command, L'\\')) {
            return false;
        }
    }

    return wide_string_append_char(command, L'"');
}

static wchar_t *duplicate_wide(const wchar_t *value) {
    size_t length = wcslen(value) + 1;
    wchar_t *copy = (wchar_t *)malloc(length * sizeof(wchar_t));
    if (copy == NULL) {
        return NULL;
    }

    memcpy(copy, value, length * sizeof(wchar_t));
    return copy;
}

static wchar_t *module_path(void) {
    DWORD capacity = 512;
    for (;;) {
        wchar_t *buffer = (wchar_t *)malloc(capacity * sizeof(wchar_t));
        if (buffer == NULL) {
            return NULL;
        }

        DWORD length = GetModuleFileNameW(NULL, buffer, capacity);
        if (length == 0) {
            free(buffer);
            return NULL;
        }

        if (length < capacity - 1) {
            return buffer;
        }

        free(buffer);
        if (capacity > 32768) {
            return NULL;
        }
        capacity *= 2;
    }
}

static wchar_t *parent_directory(const wchar_t *path) {
    wchar_t *directory = duplicate_wide(path);
    if (directory == NULL) {
        return NULL;
    }

    wchar_t *last_backslash = wcsrchr(directory, L'\\');
    wchar_t *last_slash = wcsrchr(directory, L'/');
    wchar_t *separator = last_backslash;
    if (last_slash != NULL && (separator == NULL || last_slash > separator)) {
        separator = last_slash;
    }
    if (separator == NULL) {
        free(directory);
        return NULL;
    }

    *separator = L'\0';
    return directory;
}

static wchar_t *join_path(const wchar_t *directory, const wchar_t *name) {
    size_t directory_length = wcslen(directory);
    size_t name_length = wcslen(name);
    bool needs_separator =
        directory_length > 0 && directory[directory_length - 1] != L'\\' &&
        directory[directory_length - 1] != L'/';
    size_t total = directory_length + (needs_separator ? 1 : 0) + name_length + 1;

    wchar_t *path = (wchar_t *)malloc(total * sizeof(wchar_t));
    if (path == NULL) {
        return NULL;
    }

    wcscpy_s(path, total, directory);
    if (needs_separator) {
        wcscat_s(path, total, L"\\");
    }
    wcscat_s(path, total, name);
    return path;
}

static bool file_exists(const wchar_t *path) {
    DWORD attributes = GetFileAttributesW(path);
    return attributes != INVALID_FILE_ATTRIBUTES &&
           (attributes & FILE_ATTRIBUTE_DIRECTORY) == 0;
}

static wchar_t *launcher_log_path(void) {
    wchar_t base[MAX_PATH];
    DWORD length = GetEnvironmentVariableW(L"LOCALAPPDATA", base, MAX_PATH);
    if (length == 0 || length >= MAX_PATH) {
        length = GetTempPathW(MAX_PATH, base);
        if (length == 0 || length >= MAX_PATH) {
            return NULL;
        }
    }

    wchar_t *log_directory = join_path(base, LOG_SUBDIR);
    if (log_directory == NULL) {
        return NULL;
    }

    if (!CreateDirectoryW(log_directory, NULL)) {
        DWORD error = GetLastError();
        if (error != ERROR_ALREADY_EXISTS) {
            free(log_directory);
            return NULL;
        }
    }

    wchar_t *log_path = join_path(log_directory, LOG_FILE);
    free(log_directory);
    return log_path;
}

static bool write_log_header(
    HANDLE log_handle,
    const wchar_t *uv_path,
    const wchar_t *script_path,
    int argc,
    wchar_t **argv) {
    WideString header = {0};
    bool ok = wide_string_append(&header, L"pxl Windows launcher\r\nuv: ") &&
              wide_string_append(&header, uv_path) &&
              wide_string_append(&header, L"\r\nscript: ") &&
              wide_string_append(&header, script_path) &&
              wide_string_append(&header, L"\r\narguments:\r\n");
    for (int index = 1; ok && index < argc; index++) {
        ok = wide_string_append(&header, L"  ") &&
             wide_string_append(&header, argv[index]) &&
             wide_string_append(&header, L"\r\n");
    }
    ok = ok && wide_string_append(&header, L"\r\n");

    if (!ok) {
        free(header.data);
        return false;
    }

    int utf8_length = WideCharToMultiByte(
        CP_UTF8,
        0,
        header.data,
        -1,
        NULL,
        0,
        NULL,
        NULL);
    if (utf8_length <= 1) {
        free(header.data);
        return false;
    }

    char *utf8 = (char *)malloc((size_t)utf8_length);
    if (utf8 == NULL) {
        free(header.data);
        return false;
    }

    WideCharToMultiByte(
        CP_UTF8,
        0,
        header.data,
        -1,
        utf8,
        utf8_length,
        NULL,
        NULL);

    DWORD written = 0;
    BOOL wrote = WriteFile(
        log_handle,
        utf8,
        (DWORD)(utf8_length - 1),
        &written,
        NULL);

    free(utf8);
    free(header.data);
    return wrote != FALSE;
}

static wchar_t *build_command_line(
    const wchar_t *uv_path,
    const wchar_t *script_path,
    int argc,
    wchar_t **argv) {
    WideString command = {0};
    bool ok = append_quoted_argument(&command, uv_path) &&
              append_quoted_argument(&command, L"run") &&
              append_quoted_argument(&command, L"--gui-script") &&
              append_quoted_argument(&command, script_path);

    for (int index = 1; ok && index < argc; index++) {
        ok = append_quoted_argument(&command, argv[index]);
    }

    if (!ok) {
        free(command.data);
        return NULL;
    }

    return command.data;
}

static int run_launcher(void) {
    int exit_code = 1;
    wchar_t *exe_path = NULL;
    wchar_t *app_dir = NULL;
    wchar_t *uv_path = NULL;
    wchar_t *script_path = NULL;
    wchar_t *log_path = NULL;
    wchar_t *command_line = NULL;
    wchar_t **argv = NULL;
    HANDLE log_handle = INVALID_HANDLE_VALUE;
    HANDLE nul_handle = INVALID_HANDLE_VALUE;
    PROCESS_INFORMATION process_info;
    ZeroMemory(&process_info, sizeof(process_info));

    exe_path = module_path();
    if (exe_path == NULL) {
        show_last_error(L"Could not locate pxl.exe.", GetLastError());
        goto cleanup;
    }

    app_dir = parent_directory(exe_path);
    if (app_dir == NULL) {
        show_error(L"Could not determine the pxl.exe directory.");
        goto cleanup;
    }

    uv_path = join_path(app_dir, L"uv.exe");
    script_path = join_path(app_dir, L"pxl.py");
    if (uv_path == NULL || script_path == NULL) {
        show_error(L"Out of memory while preparing launcher paths.");
        goto cleanup;
    }

    if (!file_exists(uv_path)) {
        wchar_t message[4096];
        swprintf_s(
            message,
            4096,
            L"Could not find bundled uv.exe:\n\n%ls",
            uv_path);
        show_error(message);
        goto cleanup;
    }

    if (!file_exists(script_path)) {
        wchar_t message[4096];
        swprintf_s(
            message,
            4096,
            L"Could not find pxl.py next to pxl.exe:\n\n%ls",
            script_path);
        show_error(message);
        goto cleanup;
    }

    int argc = 0;
    argv = CommandLineToArgvW(GetCommandLineW(), &argc);
    if (argv == NULL) {
        show_last_error(L"Could not parse the pxl command line.", GetLastError());
        goto cleanup;
    }

    log_path = launcher_log_path();
    if (log_path == NULL) {
        show_last_error(L"Could not create the pxl launcher log.", GetLastError());
        goto cleanup;
    }

    SECURITY_ATTRIBUTES security_attributes;
    security_attributes.nLength = sizeof(security_attributes);
    security_attributes.lpSecurityDescriptor = NULL;
    security_attributes.bInheritHandle = TRUE;

    log_handle = CreateFileW(
        log_path,
        GENERIC_WRITE,
        FILE_SHARE_READ,
        &security_attributes,
        CREATE_ALWAYS,
        FILE_ATTRIBUTE_NORMAL,
        NULL);
    if (log_handle == INVALID_HANDLE_VALUE) {
        show_last_error(L"Could not open the pxl launcher log.", GetLastError());
        goto cleanup;
    }

    nul_handle = CreateFileW(
        L"NUL",
        GENERIC_READ,
        FILE_SHARE_READ | FILE_SHARE_WRITE,
        &security_attributes,
        OPEN_EXISTING,
        FILE_ATTRIBUTE_NORMAL,
        NULL);
    if (nul_handle == INVALID_HANDLE_VALUE) {
        show_last_error(L"Could not open NUL for pxl launcher input.", GetLastError());
        goto cleanup;
    }

    write_log_header(log_handle, uv_path, script_path, argc, argv);

    command_line = build_command_line(uv_path, script_path, argc, argv);
    if (command_line == NULL) {
        show_error(L"Out of memory while building the pxl command line.");
        goto cleanup;
    }

    STARTUPINFOW startup_info;
    ZeroMemory(&startup_info, sizeof(startup_info));
    startup_info.cb = sizeof(startup_info);
    startup_info.dwFlags = STARTF_USESTDHANDLES;
    startup_info.hStdInput = nul_handle;
    startup_info.hStdOutput = log_handle;
    startup_info.hStdError = log_handle;

    BOOL created = CreateProcessW(
        uv_path,
        command_line,
        NULL,
        NULL,
        TRUE,
        CREATE_NO_WINDOW,
        NULL,
        app_dir,
        &startup_info,
        &process_info);

    if (!created) {
        show_last_error(L"Could not start pxl through bundled uv.exe.", GetLastError());
        goto cleanup;
    }

    WaitForSingleObject(process_info.hProcess, INFINITE);

    DWORD child_exit_code = 1;
    if (!GetExitCodeProcess(process_info.hProcess, &child_exit_code)) {
        show_last_error(L"Could not read the pxl exit code.", GetLastError());
        goto cleanup;
    }

    exit_code = (int)child_exit_code;
    if (child_exit_code != 0) {
        wchar_t message[4096];
        swprintf_s(
            message,
            4096,
            L"pxl exited with code %lu.\n\nDetails were written to:\n%ls",
            child_exit_code,
            log_path);
        show_error(message);
    }

cleanup:
    if (process_info.hThread != NULL) {
        CloseHandle(process_info.hThread);
    }
    if (process_info.hProcess != NULL) {
        CloseHandle(process_info.hProcess);
    }
    if (nul_handle != INVALID_HANDLE_VALUE) {
        CloseHandle(nul_handle);
    }
    if (log_handle != INVALID_HANDLE_VALUE) {
        CloseHandle(log_handle);
    }
    if (argv != NULL) {
        LocalFree(argv);
    }
    free(command_line);
    free(log_path);
    free(script_path);
    free(uv_path);
    free(app_dir);
    free(exe_path);
    return exit_code;
}

int WINAPI wWinMain(
    HINSTANCE instance,
    HINSTANCE previous_instance,
    PWSTR command_line,
    int show_command) {
    (void)instance;
    (void)previous_instance;
    (void)command_line;
    (void)show_command;
    return run_launcher();
}
