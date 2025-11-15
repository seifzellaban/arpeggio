from math import sqrt

import mido
import pygame
from pygame import mixer
import tkinter as tk
from tkinter import filedialog
from collections import deque

import piano_lists as pl

pygame.mixer.pre_init(
    frequency=44100,  # Standard sample rate
    size=-16,  # 16-bit audio
    channels=2,  # Stereo
    buffer=1024,  # Smaller buffer for lower latency
)

pygame.init()

pygame.mixer.set_num_channels(2048)

font = pygame.font.Font("assets/Terserah.ttf", 48)
medium_font = pygame.font.Font("assets/Terserah.ttf", 28)
small_font = pygame.font.Font("assets/Terserah.ttf", 16)
real_small_font = pygame.font.Font("assets/Terserah.ttf", 10)
FPS = 60
timer = pygame.time.Clock()
WIDTH = 52 * 35
HEIGHT = 550
FADEOUT_TIME = 300  # Used for smoother stop
LOOK_AHEAD_MS = 4000
FALL_DISTANCE = HEIGHT - 300 - 120  # Distance notes fall (from header to keys)
screen = pygame.display.set_mode([WIDTH, HEIGHT])
white_sounds = []
black_sounds = []
active_whites = []
active_blacks = []
left_oct = 4
right_oct = 5

key_press_times = deque(maxlen=2)


g_active_channels = []
playback_active_channels = []

sustain_pedal_down = False
sustained_notes = []


playback_messages = []
playback_start_time = 0
current_msg_index = 0
playback_active = False
NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

left_hand = pl.left_hand
right_hand = pl.right_hand
piano_notes = pl.piano_notes
white_notes = pl.white_notes
black_notes = pl.black_notes
black_labels = pl.black_labels


LIMITER_THRESHOLD = 32
BASE_NOTE_VOLUME = 0.4

WHITE_NOTE_COLOR = (0, 255, 255)  # Cyan
BLACK_NOTE_COLOR = (255, 0, 255)  # Magenta
WHITE_NOTE_HIT_COLOR = (0, 200, 0)  # Green when hit
BLACK_NOTE_HIT_COLOR = (0, 255, 0)  # Bright green when hit



for note in white_notes:
    sound = mixer.Sound(f"assets/notes/{note}.wav")
    white_sounds.append(sound)

for note in black_notes:
    sound = mixer.Sound(f"assets/notes/{note}.wav")
    black_sounds.append(sound)

pygame.display.set_caption("Arpeggio")

root = tk.Tk()
root.withdraw()  # Hides the small root window


white_note_map = {note_name: index for index, note_name in enumerate(white_notes)}
black_note_map = {note_name: index for index, note_name in enumerate(black_labels)}


def midi_to_note_name(midi_num):
    if 0 <= midi_num <= 127:
        octave = (midi_num // 12) - 1
        note_index = midi_num % 12
        note_name = NOTE_NAMES[note_index]
        return f"{note_name}{octave}"
    return None


def load_midi_file(filepath):
    global playback_messages, current_msg_index, playback_active
    try:
        mid = mido.MidiFile(filepath)
    except Exception as e:
        print(f"Error loading MIDI file: {e}")
        return False

    playback_messages = []
    current_time_sec = 0.0
    active_notes = {}  # msg.note -> (start_time_sec, velocity)

    for msg in mid:
        current_time_sec += msg.time
        if msg.type == "note_on":
            if msg.velocity > 0:
                active_notes[msg.note] = (current_time_sec, msg.velocity)
            else:
                # velocity 0 is note_off
                if msg.note in active_notes:
                    start_sec, velocity = active_notes.pop(msg.note)
                    duration_sec = current_time_sec - start_sec
                    start_ms = start_sec * 1000
                    duration_ms = duration_sec * 1000
                    note_name = midi_to_note_name(msg.note)
                    if note_name:
                        if note_name in black_note_map:
                            index = black_note_map[note_name]
                            note_type = "black"
                        elif note_name in white_note_map:
                            index = white_note_map[note_name]
                            note_type = "white"
                        else:
                            continue
                        end_ms = start_ms + duration_ms
                        playback_messages.append((start_ms, end_ms, index, note_type, velocity))
        elif msg.type == "note_off":
            if msg.note in active_notes:
                start_sec, velocity = active_notes.pop(msg.note)
                duration_sec = current_time_sec - start_sec
                start_ms = start_sec * 1000
                duration_ms = duration_sec * 1000
                note_name = midi_to_note_name(msg.note)
                if note_name:
                    if note_name in black_note_map:
                        index = black_note_map[note_name]
                        note_type = "black"
                    elif note_name in white_note_map:
                        index = white_note_map[note_name]
                        note_type = "white"
                    else:
                        continue
                    end_ms = start_ms + duration_ms
                    playback_messages.append((start_ms, end_ms, index, note_type, velocity))

    playback_messages.sort(key=lambda x: x[0])
    current_msg_index = 0
    playback_active = False
    print(f"Loaded {len(playback_messages)} notes from {filepath}")
    return True


def play_note_with_limiter(sound_to_play, velocity):
    """
    Plays a sound with a more granular "soft" dynamic limiter.
    Assumes g_active_channels has been pruned *outside* this function.
    """
    global g_active_channels
    num_playing = len(g_active_channels)

    limiter_factor = 1.0
    if num_playing > LIMITER_THRESHOLD:
        ratio = LIMITER_THRESHOLD / num_playing
        limiter_factor = sqrt(ratio)

    velocity_factor = velocity / 127.0

    final_volume = (BASE_NOTE_VOLUME * limiter_factor) * velocity_factor

    channel = pygame.mixer.find_channel()
    if channel:
        channel.set_volume(final_volume)
        channel.play(sound_to_play)
        g_active_channels.append(channel)
        return channel
    else:
        print("WARNING: No free channels, note dropped.")
        return None


def draw_falling_notes(now_ms):
    """
    Draw notes where the BOTTOM (start_time) is fixed at key level,
    and the TOP (end_time) extends upward based on duration.
    Notes stay visible until their TOP reaches the key line.
    """
    look_ahead_ms = LOOK_AHEAD_MS
    key_line_y = HEIGHT - 300
    visible_notes = []
    
    for i in range(current_msg_index, len(playback_messages)):
        start_ms, end_ms, index, note_type, velocity = playback_messages[i]
        
        # Skip notes where end_time has already passed (note completely played)
        if end_ms < now_ms:
            continue
            
        if start_ms > now_ms + look_ahead_ms:
            break
        
        # Show notes from look-ahead until end_time reaches keys
        if start_ms <= now_ms + look_ahead_ms:
            visible_notes.append(playback_messages[i])

    # Sort by height descending (taller notes behind)
    visible_notes.sort(key=lambda x: -(x[1] - x[0]))

    for start_ms, end_ms, index, note_type, velocity in visible_notes:
        # Calculate the BOTTOM of the note (where it will hit the keys)
        time_to_start = start_ms - now_ms
        start_progress = 1 - (time_to_start / look_ahead_ms)
        bottom_y = 120 + (start_progress * FALL_DISTANCE)
        
        # Calculate the TOP of the note (when the note ends)
        time_to_end = end_ms - now_ms
        end_progress = 1 - (time_to_end / look_ahead_ms)
        top_y = 120 + (end_progress * FALL_DISTANCE)
        
        # Calculate X position and width
        if note_type == "white":
            x_pos = index * 35 + 7.5
            width = 20
            falling_color = WHITE_NOTE_COLOR
            active_color = WHITE_NOTE_HIT_COLOR
        else:  # black
            black_x_positions = [
                23,93,163,198,233,303,338,408,443,478,548,583,653,688,723,
                793,828,898,933,968,1038,1073,1143,1178,1213,1283,1318,1388,1423,1458,
                1528,1563,1633,1668,1703,1773
            ]
            x_pos = black_x_positions[index] + 2
            width = 20
            falling_color = BLACK_NOTE_COLOR
            active_color = BLACK_NOTE_HIT_COLOR
        
        # Determine if the bottom has hit the keys
        bottom_has_hit = bottom_y >= key_line_y
        
        # Determine if the top has reached the keys (note should disappear)
        top_has_hit = top_y >= key_line_y
        
        if top_has_hit:
            # Note is completely consumed, don't draw anything
            continue
        
        # Calculate what portion of the note is visible
        visible_top = max(120, top_y)
        
        if not bottom_has_hit:
            # BEFORE BOTTOM HITS: Draw the entire falling note in original color
            visible_bottom = min(bottom_y, key_line_y)
            visible_height = visible_bottom - visible_top
            if visible_height > 0:
                pygame.draw.rect(screen, falling_color, [x_pos, visible_top, width, visible_height])
        else:
            # AFTER BOTTOM HITS: Split into two parts
            
            # Part 1: Above the key line (falling color)
            if top_y < key_line_y:
                above_top = visible_top
                above_bottom = min(bottom_y, key_line_y)
                above_height = above_bottom - above_top
                if above_height > 0:
                    pygame.draw.rect(screen, falling_color, [x_pos, above_top, width, above_height])
            
            # Part 2: At/below the key line (active color) - this is the "played" part
            if bottom_y > key_line_y:
                played_top = key_line_y
                played_bottom = bottom_y
                played_height = played_bottom - played_top
                if played_height > 0:
                    pygame.draw.rect(screen, active_color, [x_pos, played_top, width, played_height])


def draw_piano(whites, blacks):
    white_rects = []
    for i in range(52):
        rect = pygame.draw.rect(screen, "white", [i * 35, HEIGHT - 300, 35, 300], 0, 2)
        white_rects.append(rect)
        pygame.draw.rect(screen, "black", [i * 35, HEIGHT - 300, 35, 300], 2, 2)
        key_label = small_font.render(white_notes[i], True, "black")
        screen.blit(key_label, (i * 35 + 3, HEIGHT - 20))
    skip_count = 0
    last_skip = 2
    skip_track = 2
    black_rects = []
    for i in range(36):
        rect = pygame.draw.rect(
            screen,
            "black",
            [23 + (i * 35) + (skip_count * 35), HEIGHT - 300, 24, 200],
            0,
            2,
        )
        for q in range(len(blacks)):
            if blacks[q][0] == i:
                if blacks[q][1] != 0:
                    pygame.draw.rect(
                        screen,
                        "green",
                        [23 + (i * 35) + (skip_count * 35), HEIGHT - 300, 24, 200],
                        2,
                        2,
                    )
                    if blacks[q][1] > 0:
                        blacks[q][1] -= 1

        key_label = real_small_font.render(black_labels[i], True, "white")
        screen.blit(key_label, (25 + (i * 35) + (skip_count * 35), HEIGHT - 120))
        black_rects.append(rect)
        skip_track += 1
        if last_skip == 2 and skip_track == 3:
            last_skip = 3
            skip_track = 0
            skip_count += 1
        elif last_skip == 3 and skip_track == 2:
            last_skip = 2
            skip_track = 0
            skip_count += 1

    next_whites = []
    for i in range(len(whites)):
        if whites[i][1] > 0:
            j = whites[i][0]
            pygame.draw.rect(screen, "green", [j * 35, HEIGHT - 100, 35, 100], 2, 2)
            whites[i][1] -= 1
            if whites[i][1] > 0:
                next_whites.append(whites[i])

    next_blacks = []
    black_x_positions = [
        23,93,163,198,233,303,338,408,443,478,548,583,653,688,723,
        793,828,898,933,968,1038,1073,1143,1178,1213,1283,1318,1388,1423,1458,
        1528,1563,1633,1668,1703,1773
    ]
    for i in range(len(blacks)):
        if blacks[i][1] > 0:
            j = blacks[i][0]
            pygame.draw.rect(
                screen,
                "green",
                [black_x_positions[j], HEIGHT - 300, 24, 200],
                2,
                2,
            )
            blacks[i][1] -= 1
            if blacks[i][1] > 0:
                next_blacks.append(blacks[i])

    return white_rects, black_rects, next_whites, next_blacks


def draw_hand(oct, hand):
    base_x = oct * 245
    rect_x = base_x - 175
    pygame.draw.rect(screen, "dark gray", [rect_x, HEIGHT - 60, 245, 30], 0, 4)
    pygame.draw.rect(screen, "black", [rect_x, HEIGHT - 60, 245, 30], 4, 4)
    # White keys
    white_positions = [
        (base_x - 165, hand[0]),
        (base_x - 130, hand[2]),
        (base_x - 95, hand[4]),
        (base_x - 60, hand[5]),
        (base_x - 25, hand[7]),
        (base_x + 10, hand[9]),
        (base_x + 45, hand[11]),
    ]
    for x, note in white_positions:
        text = small_font.render(note, True, "white")
        screen.blit(text, (x, HEIGHT - 55))
    # Black keys
    black_positions = [
        (base_x - 148, hand[1]),
        (base_x - 113, hand[3]),
        (base_x - 43, hand[6]),
        (base_x - 8, hand[8]),
        (base_x + 27, hand[10]),
    ]
    for x, note in black_positions:
        text = small_font.render(note, True, "black")
        screen.blit(text, (x, HEIGHT - 55))

def draw_hands():
    draw_hand(left_oct, left_hand)
    draw_hand(right_oct, right_hand)


def draw_title_bar():
    pygame.draw.rect(screen, "white", [0, 0, WIDTH, 120])
    instruction_text = medium_font.render(
        "Up/Down Arrows Change Left Hand", True, "black"
    )
    screen.blit(instruction_text, (WIDTH - 500, 10))
    instruction_text2 = medium_font.render(
        "Left/Right Arrows Change Right Hand", True, "black"
    )
    screen.blit(instruction_text2, (WIDTH - 500, 50))
    instruction_text3 = medium_font.render("L to Load MIDI, S to Stop", True, "black")
    screen.blit(instruction_text3, (WIDTH - 500, 90))
    img = pygame.transform.scale(pygame.image.load("assets/logo.png"), [150, 150])
    screen.blit(img, (0, -34))
    title_text = font.render("A Project of the Resonance Committee.", True, "white")
    screen.blit(title_text, (298, 18))
    title_text = font.render("A Project of the Resonance Committee.", True, "black")
    screen.blit(title_text, (300, 20))



run = True
keys_pressed = set()
active_keyboard_notes = {}
while run:
    left_dict = {
        "Z": f"C{left_oct}",
        "S": f"C#{left_oct}",
        "X": f"D{left_oct}",
        "D": f"D#{left_oct}",
        "C": f"E{left_oct}",
        "V": f"F{left_oct}",
        "G": f"F#{left_oct}",
        "B": f"G{left_oct}",
        "H": f"G#{left_oct}",
        "N": f"A{left_oct}",
        "J": f"A#{left_oct}",
        "M": f"B{left_oct}",
    }
    right_dict = {
        "R": f"C{right_oct}",
        "5": f"C#{right_oct}",
        "T": f"D{right_oct}",
        "6": f"D#{right_oct}",
        "Y": f"E{right_oct}",
        "U": f"F{right_oct}",
        "8": f"F#{right_oct}",
        "I": f"G{right_oct}",
        "9": f"G#{right_oct}",
        "O": f"A{right_oct}",
        "0": f"A#{right_oct}",
        "P": f"B{right_oct}",
    }
    timer.tick(FPS)
    screen.fill("gray")

    g_active_channels = [ch for ch in g_active_channels if ch.get_busy()]

    now_ms = pygame.time.get_ticks() - playback_start_time
    
    # Handle channel fadeouts
    for ch, end_ms in list(playback_active_channels):
        if now_ms >= end_ms - FADEOUT_TIME:
            ch.fadeout(FADEOUT_TIME)
            playback_active_channels.remove((ch, end_ms))

    # Handle playback note triggering
    if playback_active and current_msg_index < len(playback_messages):
        while current_msg_index < len(playback_messages):
            start_ms, end_ms, index, note_type, velocity = playback_messages[
                current_msg_index
            ]
            if now_ms >= start_ms:
                sound_to_play = None
                if note_type == "black":
                    sound_to_play = black_sounds[index]
                    active_blacks.append([index, 30])
                else:
                    sound_to_play = white_sounds[index]
                    active_whites.append([index, 30])

                if sound_to_play:
                    channel = play_note_with_limiter(sound_to_play, velocity)
                    if channel:
                        playback_active_channels.append((channel, end_ms))

                current_msg_index += 1
            else:
                break

        if current_msg_index >= len(playback_messages):
            print("Playback finished.")
            playback_active = False

    # Draw falling notes BEFORE piano (so piano keys appear on top)
    if playback_active:
        draw_falling_notes(now_ms)

    # Draw piano on top of falling notes
    white_keys, black_keys, active_whites, active_blacks = draw_piano(
        active_whites, active_blacks
    )
    draw_hands()
    draw_title_bar()

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            run = False

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_SPACE:
                sustain_pedal_down = True

        if event.type == pygame.KEYUP:
            if event.key == pygame.K_SPACE:
                sustain_pedal_down = False
        # When the pedal is released, stop all sustained notes
        for channel in sustained_notes:
            channel.stop()
        sustained_notes.clear()

        if event.type == pygame.MOUSEBUTTONDOWN:
            black_key = False
            for i, key in enumerate(black_keys):
                if key.collidepoint(event.pos):
                    # Y-position relative to the key
                    relative_y = event.pos[1] - key.y
                    # Normalize to a 0-1 range, then scale to 0-127
                    velocity = int((relative_y / key.height) * 127)
                    play_note_with_limiter(black_sounds[i], velocity)
                    black_key = True
                    active_blacks.append([i, 30])
            for i, key in enumerate(white_keys):
                if key.collidepoint(event.pos) and not black_key:
                    relative_y = event.pos[1] - key.y
                    velocity = int((relative_y / key.height) * 127)
                    play_note_with_limiter(white_sounds[i], velocity)
                    active_whites.append([i, 30])

        if event.type == pygame.KEYDOWN:
            key = event.unicode.upper()
            if key not in keys_pressed:
                keys_pressed.add(key)
                note_name = left_dict.get(key) or right_dict.get(key)

                if note_name and note_name not in active_keyboard_notes:
                    # --- New velocity logic ---
                    now = pygame.time.get_ticks()
                    velocity = 90  # Default for the very first note
                    if key_press_times:
                        diff = now - key_press_times[-1]
                        min_diff = 50
                        max_diff = 400
                        min_vel = 70
                        max_vel = 127
                        if diff <= min_diff:
                            velocity = max_vel
                        elif diff >= max_diff:
                            velocity = min_vel
                        else:
                            velocity = int(
                                max_vel
                                - ((diff - min_diff) / (max_diff - min_diff))
                                * (max_vel - min_vel)
                            )
                    key_press_times.append(now)
                    # --- End of new logic ---

                    # If key already active, stop it and remove highlights
                    if note_name in active_keyboard_notes:
                        old_channel = active_keyboard_notes.pop(note_name)
                        old_channel.stop()
                        if "#" in note_name:
                            index = black_labels.index(note_name)
                            active_blacks = [b for b in active_blacks if b[0] != index]
                        else:
                            index = white_notes.index(note_name)
                            active_whites = [w for w in active_whites if w[0] != index]

                    if "#" in note_name:
                        index = black_labels.index(note_name)
                        sound_to_play = black_sounds[index]
                        channel = play_note_with_limiter(sound_to_play, velocity)
                        if channel:
                            active_keyboard_notes[note_name] = channel
                            if not sustain_pedal_down:
                                active_blacks.append([index, 30])
                    else:
                        index = white_notes.index(note_name)
                        sound_to_play = white_sounds[index]
                        channel = play_note_with_limiter(sound_to_play, velocity)
                        if channel:
                            active_keyboard_notes[note_name] = channel
                            if not sustain_pedal_down:
                                active_whites.append([index, 30])

        if event.type == pygame.KEYUP:
            key = event.unicode.upper()
            if key in keys_pressed:
                keys_pressed.remove(key)

            note_name = left_dict.get(key) or right_dict.get(key)

            if note_name and note_name in active_keyboard_notes:
                channel = active_keyboard_notes.pop(note_name)
                if sustain_pedal_down:
                    sustained_notes.append(channel)
                else:
                    channel.fadeout(FADEOUT_TIME)

                if "#" in note_name:
                    index = black_labels.index(note_name)
                    for i, black in enumerate(active_blacks):
                        if black[0] == index:
                            active_blacks.pop(i)
                            break
                else:
                    index = white_notes.index(note_name)
                    for i, white in enumerate(active_whites):
                        if white[0] == index:
                            active_whites.pop(i)
                            break

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_l:
                # Open file dialog
                midi_file_path = filedialog.askopenfilename(
                    initialdir="assets/MIDI/",
                    title="Select a MIDI File",
                    filetypes=(("MIDI Files", "*.mid"), ("All files", "*.*")),
                )
                if midi_file_path:  # If a file was selected
                    if load_midi_file(midi_file_path):
                        print("Starting visualization...")
                        # Start with negative time so notes fall into position
                        playback_start_time = pygame.time.get_ticks() + LOOK_AHEAD_MS
                        playback_active = True
                        current_msg_index = 0
                        print(f"Notes will reach keys in {LOOK_AHEAD_MS}ms")
                    else:
                        print(f"Could not play {midi_file_path}")

            if event.key == pygame.K_s:
                playback_active = False
                for channel, end_ms in playback_active_channels:
                    channel.fadeout(FADEOUT_TIME)
                playback_active_channels.clear()

            if event.key == pygame.K_RIGHT:
                if right_oct < 8:
                    right_oct += 1
            if event.key == pygame.K_LEFT:
                if right_oct > 0:
                    right_oct -= 1
            if event.key == pygame.K_UP:
                if left_oct < 8:
                    left_oct += 1
            if event.key == pygame.K_DOWN:
                if left_oct > 0:
                    left_oct -= 1

    pygame.display.flip()
pygame.quit()
