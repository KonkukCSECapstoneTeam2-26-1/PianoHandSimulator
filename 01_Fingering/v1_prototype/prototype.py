import mido
import time

# 1. Note 및 Chord 클래스 정의
class Note:
    def __init__(self, pitch, velocity, start_ms, duration_ms):
        self.pitch = pitch
        self.velocity = velocity
        self.start_ms = start_ms
        self.duration_ms = duration_ms
        self.hand = None  # 0: Left, 1: Right
        self.finger = 0   # 1~5

    def __repr__(self):
        return f"Note(P:{self.pitch}, H:{'L' if self.hand==0 else 'R'}, F:{self.finger})"

class Chord:
    def __init__(self, start_ms):
        self.start_ms = start_ms
        self.notes = []

    def add_note(self, note):
        self.notes.append(note)

# 2. MIDI 파싱 및 그룹화 (General Logic)
def parse_midi_to_chords(file_path, chord_threshold_ms=30):
    mid = mido.MidiFile(file_path)
    notes = []
    active_notes = {}
    current_time_ms = 0
    # Default tempo: 500,000 microseconds per beat (120 BPM)
    tempo = 500000

    for i, track in enumerate(mid.tracks):
        track_time_ms = 0
        for msg in track:
            # Note: mido's msg.time is delta time in ticks.
            # Convert ticks to seconds based on current tempo and ticks_per_beat.
            # We must track tempo changes. 
            # In a simple prototype, we'll use a fixed conversion or track it.
            delta_ms = mido.tick2second(msg.time, mid.ticks_per_beat, tempo) * 1000
            track_time_ms += delta_ms
            
            if msg.type == 'set_tempo':
                tempo = msg.tempo
            
            if msg.type == 'note_on' and msg.velocity > 0:
                active_notes[msg.note] = (track_time_ms, msg.velocity)
            elif (msg.type == 'note_off') or (msg.type == 'note_on' and msg.velocity == 0):
                if msg.note in active_notes:
                    start_time, velocity = active_notes.pop(msg.note)
                    duration = track_time_ms - start_time
                    notes.append(Note(msg.note, velocity, start_time, duration))

    # Sort all notes by start time
    notes.sort(key=lambda x: x.start_ms)

    # Group into chords
    chords = []
    if not notes: return chords

    current_chord = Chord(notes[0].start_ms)
    current_chord.add_note(notes[0])
    chords.append(current_chord)

    for i in range(1, len(notes)):
        # If the note starts very close to the current chord's start time, group it
        if notes[i].start_ms - current_chord.start_ms <= chord_threshold_ms:
            current_chord.add_note(notes[i])
        else:
            current_chord = Chord(notes[i].start_ms)
            current_chord.add_note(notes[i])
            chords.append(current_chord)
            
    return chords

# 3. 양손 분할 (Hand Splitter - Heuristic)
def split_hands(chords):
    # Simple split at Middle C (60)
    for chord in chords:
        chord.notes.sort(key=lambda x: x.pitch)
        for note in chord.notes:
            if note.pitch < 60:
                note.hand = 0 # Left
            else:
                note.hand = 1 # Right

# 4. 운지법 DP 알고리즘 (Simplified)
def solve_fingering(hand_notes):
    if not hand_notes: return
    
    n = len(hand_notes)
    # dp[note_idx][finger(1-5)]
    dp = [[float('inf')] * 6 for _ in range(n)]
    parent = [[0] * 6 for _ in range(n)]

    # Initialize first note
    for f in range(1, 6):
        dp[0][f] = 0 

    # Cost Function: Distance between fingers
    # finger 1: Thumb, 5: Pinky
    def get_cost(prev_pitch, prev_f, curr_pitch, curr_f):
        pitch_diff = curr_pitch - prev_pitch
        finger_diff = curr_f - prev_f
        
        # Physical constraints (Simplified)
        # Thumb(1) can reach far, others less so
        if finger_diff == 0:
            return 10 if pitch_diff != 0 else 0 # Penalty for repeating same finger on different pitch
        
        # Natural stretch (e.g., thumb to pinky can easily cover an octave)
        # pitch_diff should roughly align with finger_diff
        expected_pitch_diff = finger_diff * 2 
        stretch_cost = abs(pitch_diff - expected_pitch_diff)
        
        return stretch_cost

    # Fill DP table
    for i in range(1, n):
        for curr_f in range(1, 6):
            for prev_f in range(1, 6):
                cost = get_cost(hand_notes[i-1].pitch, prev_f, hand_notes[i].pitch, curr_f)
                new_cost = dp[i-1][prev_f] + cost
                if new_cost < dp[i][curr_f]:
                    dp[i][curr_f] = new_cost
                    parent[i][curr_f] = prev_f

    # Backtrack to find best sequence
    best_f = 1
    min_total_cost = float('inf')
    for f in range(1, 6):
        if dp[n-1][f] < min_total_cost:
            min_total_cost = dp[n-1][f]
            best_f = f

    for i in range(n-1, -1, -1):
        hand_notes[i].finger = best_f
        best_f = parent[i][best_f]

# Main execution
def run_prototype():
    # 1. Create dummy MIDI file for testing
    mid = mido.MidiFile()
    track = mido.MidiTrack()
    mid.tracks.append(track)
    
    # C4(60), E4(64), G4(67) chord (Note On at the same time)
    track.append(mido.Message('note_on', note=60, velocity=64, time=0))
    track.append(mido.Message('note_on', note=64, velocity=64, time=0))
    track.append(mido.Message('note_on', note=67, velocity=64, time=0))
    # Release after 1 beat (480 ticks)
    track.append(mido.Message('note_off', note=60, velocity=64, time=480))
    track.append(mido.Message('note_off', note=64, velocity=64, time=0))
    track.append(mido.Message('note_off', note=67, velocity=64, time=0))
    
    # D5(74) single note after short gap
    track.append(mido.Message('note_on', note=74, velocity=64, time=120))
    track.append(mido.Message('note_off', note=74, velocity=64, time=480))
    
    mid.save('test.mid')
    print("Created test.mid")

    # 2. Parse and Solve
    chords = parse_midi_to_chords('test.mid')
    split_hands(chords)
    
    # Process Right Hand notes
    right_notes = [n for c in chords for n in c.notes if n.hand == 1]
    solve_fingering(right_notes)
    
    # Process Left Hand notes
    left_notes = [n for c in chords for n in c.notes if n.hand == 0]
    solve_fingering(left_notes)

    # 3. Print Results
    print("\n--- Fingering Optimization Result ---")
    for c in chords:
        print(f"Time {int(c.start_ms):4d}ms | Chord: {c.notes}")

if __name__ == "__main__":
    run_prototype()
