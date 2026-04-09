# Principle Template Guide

## Purpose

Principle entries define rules and guidelines to follow. They establish:
- What should be done
- Why it matters
- When it applies
- How to implement

## When to Create

Create a principle when:
- Establishing team conventions
- Defining coding standards
- Documenting architectural decisions
- Setting security requirements
- Defining quality standards

## Structure

### 1. Definition

State the rule clearly:
- What is the guideline?
- What does it require?
- What does it prohibit?

**Example:**
```markdown
## Definition
All external inputs must be validated before processing, including:
- API request parameters and body
- File uploads and their metadata
- User form submissions
- External service responses
- Environment variables
```

### 2. Rationale

Explain why it matters:
- What problems does it prevent?
- What benefits does it provide?
- What are the risks of not following?

**Example:**
```markdown
## Rationale
Input validation prevents:
- Injection attacks (SQL, command, XSS)
- Data corruption and integrity issues
- Unexpected application behavior
- Security vulnerabilities
- Hard-to-debug errors from invalid data

The cost of validation is minimal compared to the cost of security 
breaches or data corruption incidents.
```

### 3. Application

Describe how to apply:
- When should this be used?
- How should it be implemented?
- What are concrete examples?

**Example:**
````markdown
## Application

### API Endpoints
Use Pydantic models for automatic validation:
```python
from pydantic import BaseModel, validator

class UserCreate(BaseModel):
    username: str
    email: str
    
    @validator('username')
    def validate_username(cls, v):
        if len(v) < 3:
            raise ValueError('Username must be at least 3 characters')
        return v
```

### File Uploads
- Check file type against whitelist
- Verify file size limits
- Scan for malware if applicable
- Validate file content structure
````

### 4. Exceptions

Document when it doesn't apply:
- Are there valid exceptions?
- What conditions justify them?
- How to handle them safely?

**Example:**
```markdown
## Exceptions

This principle may be relaxed when:
- Internal service-to-service calls within a trusted network
- Data coming from internal databases (already validated on entry)
- Performance-critical paths where validation was done upstream

Even in exceptions, consider:
- Defense in depth - validate at multiple layers
- Documentation - note why validation is skipped
- Monitoring - watch for unexpected data
```

### 5. References

Link to supporting material:
- External documentation
- Internal guidelines
- Related principles
- Case studies

**Example:**
```markdown
## References
- [OWASP Input Validation Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html)
- Company Security Guidelines v2.3
- Related: Principle "Defense in Depth"
- Experience: "2024-03-15-sql-injection-incident"
```

## Writing Tips

1. **Be prescriptive** - State what to do, not just what to avoid
2. **Explain why** - The reasoning is as important as the rule
3. **Provide examples** - Show both good and bad examples
4. **Acknowledge nuance** - Document exceptions and edge cases
5. **Keep current** - Update as practices evolve

## Priority Levels

- **High** - Must follow, critical for security/correctness
- **Medium** - Should follow, important for quality/maintainability
- **Low** - Nice to follow, improves consistency

## Example Entry

See [SKILL.md](../SKILL.md) for a complete example.
