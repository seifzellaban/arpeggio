from math import sqrt

import mido
import pygame
from pygame import mixer

import piano_lists as pl

pygame.mixer.pre_init(
    frequency=44100,  # Standard sample rate
    size=-16,  # 16-bit audio
    channels=2,  # Stereo
    buffer=2048,
)

pygame.init()

pygame.mixer.set_num_channels(512)

font = pygame.font.Font("assets/Terserah.ttf", 48)
medium_font = pygame.font.Font("assets/Terserah.ttf", 28)
small_font = pygame.font.Font("assets/Terserah.ttf", 16)
real_small_font = pygame.font.Font("assets/Terserah.ttf", 10)
fps = 60
timer = pygame.time.Clock()
WIDTH = 52 * 35
HEIGHT = 400
screen = pygame.display.set_mode([WIDTH, HEIGHT])
white_sounds = []
black_sounds = []
active_whites = []
active_blacks = []
left_oct = 4
right_oct = 5

g_active_channels = []

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


LIMITER_THRESHOLD = 16
BASE_NOTE_VOLUME = 0.6


for i in range(len(white_notes)):
    sound = mixer.Sound(f"assets/notes/{white_notes[i]}.wav")
    white_sounds.append(sound)

for i in range(len(black_notes)):
    sound = mixer.Sound(f"assets/notes/{black_notes[i]}.wav")
    black_sounds.append(sound)

pygame.display.set_caption("Arpeggio")


white_note_map = {note_name: index for index, note_name in enumerate(white_notes)}
black_note_map = {note_name: index for index, note_name in enumerate(black_labels)}


def midi_to_note_name(midi_num):
    if not (0 <= midi_num <= 127):
        return None
    octave = (midi_num // 12) - 1
    note_index = midi_num % 12
    note_name = NOTE_NAMES[note_index]
    return f"{note_name}{octave}"


def load_midi_file(filepath):
    global playback_messages, current_msg_index, playback_active
    try:
        mid = mido.MidiFile(filepath)
    except Exception as e:
        print(f"Error loading MIDI file: {e}")
        return False

    playback_messages = []
    current_time_sec = 0.0

    for msg in mid:
        current_time_sec += msg.time
        if msg.type == "note_on" and msg.velocity > 0:
            note_name = midi_to_note_name(msg.note)
            velocity = msg.velocity
            if note_name:
                if note_name in black_note_map:
                    index = black_note_map[note_name]
                    note_type = "black"
                    playback_messages.append(
                        (current_time_sec * 1000, index, note_type, velocity)
                    )
                elif note_name in white_note_map:
                    index = white_note_map[note_name]
                    note_type = "white"
                    playback_messages.append(
                        (current_time_sec * 1000, index, note_type, velocity)
                    )
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

        # --- (old logic for comparison) ---
        # limiter_factor = LIMITER_THRESHOLD / (num_playing * 2 / pi)
        # The sqrt(ratio) will feel much smoother.

    velocity_factor = velocity / 127.0

    final_volume = (BASE_NOTE_VOLUME * limiter_factor) * velocity_factor

    channel = pygame.mixer.find_channel()
    if channel:
        channel.set_volume(final_volume)
        channel.play(sound_to_play)
        g_active_channels.append(channel)
        # print(len(g_active_channels))
    else:
        print("WARNING: No free channels, note dropped.")
        pass


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
                if blacks[q][1] > 0:
                    pygame.draw.rect(
                        screen,
                        "green",
                        [23 + (i * 35) + (skip_count * 35), HEIGHT - 300, 24, 200],
                        2,
                        2,
                    )
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

    for i in range(len(whites)):
        if whites[i][1] > 0:
            j = whites[i][0]
            pygame.draw.rect(screen, "green", [j * 35, HEIGHT - 100, 35, 100], 2, 2)
            whites[i][1] -= 1

    return white_rects, black_rects, whites, blacks


def draw_hands(rightOct, leftOct, rightHand, leftHand):
    # left hand
    pygame.draw.rect(
        screen, "dark gray", [(leftOct * 245) - 175, HEIGHT - 60, 245, 30], 0, 4
    )
    pygame.draw.rect(
        screen, "black", [(leftOct * 245) - 175, HEIGHT - 60, 245, 30], 4, 4
    )
    text = small_font.render(leftHand[0], True, "white")
    screen.blit(text, ((leftOct * 245) - 165, HEIGHT - 55))
    text = small_font.render(leftHand[2], True, "white")
    screen.blit(text, ((leftOct * 245) - 130, HEIGHT - 55))
    text = small_font.render(leftHand[4], True, "white")
    screen.blit(text, ((leftOct * 245) - 95, HEIGHT - 55))
    text = small_font.render(leftHand[5], True, "white")
    screen.blit(text, ((leftOct * 245) - 60, HEIGHT - 55))
    text = small_font.render(leftHand[7], True, "white")
    screen.blit(text, ((leftOct * 245) - 25, HEIGHT - 55))
    text = small_font.render(leftHand[9], True, "white")
    screen.blit(text, ((leftOct * 245) + 10, HEIGHT - 55))
    text = small_font.render(leftHand[11], True, "white")
    screen.blit(text, ((leftOct * 245) + 45, HEIGHT - 55))
    text = small_font.render(leftHand[1], True, "black")
    screen.blit(text, ((leftOct * 245) - 148, HEIGHT - 55))
    text = small_font.render(leftHand[3], True, "black")
    screen.blit(text, ((leftOct * 245) - 113, HEIGHT - 55))
    text = small_font.render(leftHand[6], True, "black")
    screen.blit(text, ((leftOct * 245) - 43, HEIGHT - 55))
    text = small_font.render(leftHand[8], True, "black")
    screen.blit(text, ((leftOct * 245) - 8, HEIGHT - 55))
    text = small_font.render(leftHand[10], True, "black")
    screen.blit(text, ((leftOct * 245) + 27, HEIGHT - 55))
    # right hand
    pygame.draw.rect(
        screen, "dark gray", [(rightOct * 245) - 175, HEIGHT - 60, 245, 30], 0, 4
    )
    pygame.draw.rect(
        screen, "black", [(rightOct * 245) - 175, HEIGHT - 60, 245, 30], 4, 4
    )
    text = small_font.render(rightHand[0], True, "white")
    screen.blit(text, ((rightOct * 245) - 165, HEIGHT - 55))
    text = small_font.render(rightHand[2], True, "white")
    screen.blit(text, ((rightOct * 245) - 130, HEIGHT - 55))
    text = small_font.render(rightHand[4], True, "white")
    screen.blit(text, ((rightOct * 245) - 95, HEIGHT - 55))
    text = small_font.render(rightHand[5], True, "white")
    screen.blit(text, ((rightOct * 245) - 60, HEIGHT - 55))
    text = small_font.render(rightHand[7], True, "white")
    screen.blit(text, ((rightOct * 245) - 25, HEIGHT - 55))
    text = small_font.render(rightHand[9], True, "white")
    screen.blit(text, ((rightOct * 245) + 10, HEIGHT - 55))
    text = small_font.render(rightHand[11], True, "white")
    screen.blit(text, ((rightOct * 245) + 45, HEIGHT - 55))
    text = small_font.render(rightHand[1], True, "black")
    screen.blit(text, ((rightOct * 245) - 148, HEIGHT - 55))
    text = small_font.render(rightHand[3], True, "black")
    screen.blit(text, ((rightOct * 245) - 113, HEIGHT - 55))
    text = small_font.render(rightHand[6], True, "black")
    screen.blit(text, ((rightOct * 245) - 43, HEIGHT - 55))
    text = small_font.render(rightHand[8], True, "black")
    screen.blit(text, ((rightOct * 245) - 8, HEIGHT - 55))
    text = small_font.render(rightHand[10], True, "black")
    screen.blit(text, ((rightOct * 245) + 27, HEIGHT - 55))


def draw_title_bar():
    instruction_text = medium_font.render(
        "Up/Down Arrows Change Left Hand", True, "black"
    )
    screen.blit(instruction_text, (WIDTH - 500, 10))
    instruction_text2 = medium_font.render(
        "Left/Right Arrows Change Right Hand", True, "black"
    )
    screen.blit(instruction_text2, (WIDTH - 500, 50))
    img = pygame.transform.scale(pygame.image.load("assets/logo.png"), [150, 150])
    screen.blit(img, (0, -34))
    title_text = font.render("A Project of the Resonance Committee.", True, "white")
    screen.blit(title_text, (298, 18))
    title_text = font.render("A Project of the Resonance Committee.", True, "black")
    screen.blit(title_text, (300, 20))



run = True
keys_pressed = set()
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
    timer.tick(fps)
    screen.fill("gray")

    g_active_channels = [ch for ch in g_active_channels if ch.get_busy()]

    if playback_active and current_msg_index < len(playback_messages):
        now_ms = pygame.time.get_ticks() - playback_start_time

        while current_msg_index < len(playback_messages):
            msg_time_ms, index, note_type, velocity = playback_messages[
                current_msg_index
            ]
            if now_ms >= msg_time_ms:
                sound_to_play = None
                if note_type == "black":
                    sound_to_play = black_sounds[index]
                    active_blacks.append([index, 30])
                else:
                    sound_to_play = white_sounds[index]
                    active_whites.append([index, 30])

                if sound_to_play:
                    play_note_with_limiter(sound_to_play, velocity)

                current_msg_index += 1
            else:
                break

        if current_msg_index >= len(playback_messages):
            print("Playback finished.")
            playback_active = False

    white_keys, black_keys, active_whites, active_blacks = draw_piano(
        active_whites, active_blacks
    )
    draw_hands(right_oct, left_oct, right_hand, left_hand)
    draw_title_bar()

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            run = False

        if event.type == pygame.MOUSEBUTTONDOWN:
            black_key = False
            for i in range(len(black_keys)):
                if black_keys[i].collidepoint(event.pos):
                    play_note_with_limiter(black_sounds[i], 127)
                    black_key = True
                    active_blacks.append([i, 30])
            for i in range(len(white_keys)):
                if white_keys[i].collidepoint(event.pos) and not black_key:
                    play_note_with_limiter(white_sounds[i], 127)
                    active_whites.append([i, 30])

        if event.type == pygame.KEYDOWN:
            key = event.unicode.upper()
            if key not in keys_pressed:
                keys_pressed.add(key)
                if key in left_dict:
                    if left_dict[key][1] == "#":
                        index = black_labels.index(left_dict[key])
                        play_note_with_limiter(black_sounds[index], 127)
                        active_blacks.append([index, 30])
                    else:
                        index = white_notes.index(left_dict[key])
                        play_note_with_limiter(white_sounds[index], 127)
                        active_whites.append([index, 30])
                if key in right_dict:
                    if right_dict[key][1] == "#":
                        index = black_labels.index(right_dict[key])
                        play_note_with_limiter(black_sounds[index], 127)
                        active_blacks.append([index, 30])
                    else:
                        index = white_notes.index(right_dict[key])
                        play_note_with_limiter(white_sounds[index], 127)
                        active_whites.append([index, 30])

        if event.type == pygame.KEYUP:
            key = event.unicode.upper()
            if key in keys_pressed:
                keys_pressed.remove(key)

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_KP_0:
                midi_file_path = (
                    "assets/MIDI/Thomas_Bergersen_-_Made_of_Air_(2_Pianos).mid"
                )
                if load_midi_file(midi_file_path):
                    print("Starting playback...")
                    playback_active = True
                    playback_start_time = pygame.time.get_ticks()
                    current_msg_index = 0
                else:
                    print(f"Could not play {midi_file_path}")

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
