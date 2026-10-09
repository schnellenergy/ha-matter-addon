# JWT Security Architecture: A Simple Guide

Here is a simple, visual flow of exactly how the pieces of your app work together to keep your data secure.

## The Architecture Diagram

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant App as Flutter App (Phone)
    participant Firebase as Google Firebase Auth
    participant Backend as Custom Data Addon (Python)

    %% Phase 1: Authentication
    Note right of User: Phase 1: Getting the Token (Login)
    User->>App: 1. Enters Phone & OTP Code
    App->>Firebase: 2. Sends OTP for verification
    Firebase-->>App: 3. OTP is correct! Returns "JWT ID Token"
    Note over App: App silently saves JWT token in memory

    %% Phase 2: API Request
    Note right of User: Phase 2: Requesting Data (API Call)
    User->>App: 4. Opens "Home Setup" page
    App->>Backend: 5. GET /api/data/home_setup (Header: "Bearer <JWT Token>")
    
    Note over Backend: Backend extracts token and uses PyJWT math to verify Google's signature
    
    alt Signature is VALID
        Backend-->>App: 6. 200 OK (Returns Home Data)
        App-->>User: 7. Shows UI to user
    else Signature is INVALID or MISSING
        Backend-->>App: 6. 401 Unauthorized (Rejects request)
    end
```

---

## Who Does What Job?

Think of it like a secure VIP nightclub:

### 1. The Flutter App (The Guest)
**Job:** Needs to get inside the club to get data.
It goes to the bouncer (Firebase), proves its identity with an SMS code, gets a VIP Wristband (JWT Token), and then shows that wristband at the VIP Door (Your Python Addon).

### 2. Google Firebase (The Ticket Office / Bouncer)
**Job:** Issues the secure VIP Wristbands.
It is the only entity that can send SMS codes. When it proves a user is real, it creates the JWT Token, stamps it with an expiration time (1 hour), and mathematically signs it using a top-secret private key.

### 3. Custom Data Addon / Python Backend (The VIP Door Guard)
**Job:** Protects your data and checks the wristbands.
When the Flutter App asks for data, the backend looks at the JWT token. It **never** talks to Firebase directly to check the token. Instead, it uses simple math (`PyJWT`) and Google's public keys to instantly verify:
1. Was this token signed by Google?
2. Has it been less than 1 hour since it was created?
If both are true, it opens the door and hands over the SQLite data. If not, it slams the door (`401 Unauthorized`).
