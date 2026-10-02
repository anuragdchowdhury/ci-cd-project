package com.example.notekeeper;

import io.micrometer.core.instrument.MeterRegistry;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.net.URI;
import java.util.*;
import org.springframework.data.domain.*;
import org.springframework.http.*;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/notes")
public class NoteController {
    public record NoteInput(@NotBlank @Size(max=160) String title,
                            @NotNull @Size(max=10000) String content) { }
    public record NotePage(List<Note> items, long total, int page, int size) { }
    private final NoteRepository repository;
    private final MeterRegistry meters;
    public NoteController(NoteRepository repository, MeterRegistry meters) {
        this.repository = repository; this.meters = meters;
    }
    @GetMapping
    public NotePage list(@RequestParam(defaultValue="0") int page,
                         @RequestParam(defaultValue="20") int size) {
        if (page < 0 || size < 1 || size > 100) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Invalid page or size");
        }
        Page<Note> result = repository.findAll(PageRequest.of(page, size,
            Sort.by(Sort.Order.desc("updatedAt"), Sort.Order.asc("id"))));
        return new NotePage(result.getContent(), result.getTotalElements(), page, size);
    }
    @GetMapping("/{id}")
    public Note get(@PathVariable UUID id) { return find(id); }
    @PostMapping
    public ResponseEntity<Note> create(@Valid @RequestBody NoteInput input) {
        Note note = repository.save(new Note(input.title().trim(), input.content()));
        meters.counter("notekeeper.notes.created").increment();
        return ResponseEntity.created(URI.create("/api/notes/" + note.getId())).body(note);
    }
    @PutMapping("/{id}")
    @Transactional
    public Note update(@PathVariable UUID id, @Valid @RequestBody NoteInput input) {
        Note note = find(id); note.update(input.title().trim(), input.content()); return note;
    }
    @DeleteMapping("/{id}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    @Transactional
    public void delete(@PathVariable UUID id) {
        repository.delete(find(id)); meters.counter("notekeeper.notes.deleted").increment();
    }
    private Note find(UUID id) {
        return repository.findById(id).orElseThrow(() ->
            new ResponseStatusException(HttpStatus.NOT_FOUND, "Note not found"));
    }
}
