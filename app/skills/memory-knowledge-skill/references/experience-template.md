# Experience Template Guide

## Purpose

Experience entries capture lessons learned from actual practice. They document:
- What happened
- What was tried
- What worked or didn't
- What was learned

## When to Create

Create an experience when:
- You spent significant time solving a problem
- You discovered a non-obvious solution
- You learned something surprising
- You want to remember the approach

## Structure

### 1. Background

Describe the situation:
- What was the context?
- What problem were you solving?
- What constraints existed?

**Example:**
```markdown
## Background
The API was experiencing intermittent 500 errors under high load during 
peak hours. Initial investigation showed no obvious patterns in the logs.
```

### 2. Investigation

Document your process:
- What did you check first?
- What hypotheses did you form?
- How did you test them?

**Example:**
```markdown
## Investigation
1. Checked application logs - only generic error messages
2. Reviewed database metrics - normal CPU and memory usage
3. Analyzed request patterns - errors correlated with concurrent requests
4. Discovered connection pool exhaustion in async handlers
```

### 3. Solution

Describe what was done:
- What approach was taken?
- What code changes were made?
- What configuration was adjusted?

**Example:**
```markdown
## Solution
Implemented connection pooling with asyncpg:
- Increased pool size from 10 to 50 connections
- Added pool pre-warming on startup
- Implemented connection health checks
```

### 4. Outcome

Document the results:
- What improved?
- By how much?
- Any side effects?

**Example:**
```markdown
## Outcome
- Error rate dropped from 15% to 0.1%
- Average response time improved by 40%
- No negative impact on database performance
```

### 5. Key Takeaway

Summarize the lesson:
- What's the core insight?
- What would you do differently?
- What should others know?

**Example:**
```markdown
## Key Takeaway
Default connection pool sizes are often insufficient for production load. 
Always monitor pool utilization and size based on concurrent request 
patterns, not just total throughput.
```

### 6. Related

Link to relevant items:
- Related tasks or issues
- Code changes
- Documentation

**Example:**
```markdown
## Related
- Task: 20240401_143000_scale_api
- PR: #234
- Code: src/db/connection_pool.py
- Docs: docs/scaling.md
```

## Writing Tips

1. **Be specific** - Include actual numbers and concrete details
2. **Be honest** - Document failures as well as successes
3. **Be concise** - Focus on the key insights
4. **Be searchable** - Use clear terminology and tags

## Example Entry

See [SKILL.md](../SKILL.md) for a complete example.
