on run argv
    set targetTTY to item 1 of argv
    set marker to item 2 of argv
    tell application "Terminal"
        repeat with terminalWindow in windows
            repeat with tabIndex from 1 to count tabs of terminalWindow
                if tty of tab tabIndex of terminalWindow is targetTTY then
                    return (history of tab tabIndex of terminalWindow) & marker & (contents of tab tabIndex of terminalWindow)
                end if
            end repeat
        end repeat
    end tell
    error "no Terminal.app tab uses " & targetTTY number 64
end run
