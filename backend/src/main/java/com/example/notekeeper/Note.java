package com.example.notekeeper;

import jakarta.persistence.*;
import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "notes")
public class Note {
    @Id private UUID id;
    @Column(nullable = false, length = 160) private String title;
    @Column(nullable = false, length = 10000) private String content;
    @Column(nullable = false) private Instant createdAt;
    @Column(nullable = false) private Instant updatedAt;
    protected Note() { }
    public Note(String title, String content) {
        this.id = UUID.randomUUID();
        this.createdAt = Instant.now();
        update(title, content);
    }
    public void update(String title, String content) {
        this.title = title; this.content = content; this.updatedAt = Instant.now();
    }
    public UUID getId() { return id; }
    public String getTitle() { return title; }
    public String getContent() { return content; }
    public Instant getCreatedAt() { return createdAt; }
    public Instant getUpdatedAt() { return updatedAt; }
}
