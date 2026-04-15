# Multi-Agent System for memRAG Project

This directory contains specialized agents that work together to improve code quality, maintainability, and testing.

## Agents

### 1. Planner Agent (`planner.md`)

**Role**: Break down complex tasks into clear implementation plans

**Use Cases**:
- Planning new features
- Designing architectural changes
- Refactoring complex systems
- Planning database migrations
- Planning CI/CD improvements

**Usage**:
```bash
@planner refactor the authentication flow to use dependency injection
@planner add real-time voice transcription with session management
@planner optimize PostgreSQL queries for user search
```

**What It Does**:
- Analyzes the codebase structure
- Identifies existing patterns and dependencies
- Creates step-by-step implementation plans
- Estimates effort and risk
- Suggests verification steps

---

### 2. Test Agent (`test-agent.md`)

**Role**: Write comprehensive tests and ensure code quality

**Use Cases**:
- Writing tests for new code
- Improving test coverage
- Designing test strategies
- Analyzing test failures
- Identifying test coverage gaps

**Usage**:
```bash
@test-agent add comprehensive tests for the wiki service
@test-agent verify the RAG service with benchmarks
@test-agent add E2E tests for voice transcription flow
@test-agent analyze test coverage for the auth module
```

**What It Does**:
- Designes test cases (unit, integration, E2E)
- Writes pytest/Playwright tests
- Analyzes test coverage
- Finds untested code paths
- Suggests test improvements

---

### 3. Reviewer Agent (`reviewer.md`)

**Role**: Review code for quality, bugs, and best practices

**Use Cases**:
- Pre-merge code review
- Security review
- Performance review
- Architecture review
- Bug detection

**Usage**:
```bash
@reviewer check the recent auth changes
@reviewer review the transcription implementation
@reviewer analyze the wiki service for potential issues
@reviewer audit the code for security vulnerabilities
```

**What It Does**:
- Static code analysis
- Security vulnerability detection
- Performance analysis
- Code style and best practices review
- Bug identification

---

## Example Workflows

### Workflow 1: Implementing a New Feature

```bash
# Step 1: Plan the feature
@planner add OAuth2 authentication with Google and GitHub

# Step 2: Implement (you can do this directly or use a coder agent)

# Step 3: Review the implementation
@reviewer review the OAuth2 implementation

# Step 4: Add tests
@test-agent add tests for OAuth2 endpoints
@test-agent verify test coverage for auth module
```

### Workflow 2: Refactoring

```bash
# Step 1: Plan the refactor
@planner refactor the RAG service to support multiple collection types

# Step 2: Make the changes

# Step 3: Review
@reviewer check for performance issues in the RAG refactor

# Step 4: Test
@test-agent add tests for the new collection type support
```

### Workflow 3: Security Audit

```bash
# Security review
@reviewer audit the codebase for security vulnerabilities
@reviewer check for potential SQL injection vulnerabilities
@reviewer verify proper authentication and authorization
```

---

## Agent Capabilities

### Planner Agent
- Uses `Glob` to find relevant files
- Uses `Grep` to search code patterns
- Uses `Read` to understand code structure
- Provides detailed step-by-step plans
- Includes risk assessment
- Suggests verification steps

### Test Agent
- Uses `Bash` to run pytest
- Uses `Read` to understand code being tested
- Provides test templates for pytest and Playwright
- Analyzes test coverage
- Identifies test gaps
- Provides coverage reports

### Reviewer Agent
- Uses `Read` to review code
- Uses `Grep` to find potential issues
- Uses `mcp__ide__getDiagnostics` for real-time linting
- Provides critical warnings for security issues
- Suggests code improvements
- Estimates fix time

---

## Integration with Project

These agents are integrated into the memRAG project workflow:

1. **Planning Phase**: Use planner agent to break down tasks
2. **Implementation Phase**: Implement the planned changes
3. **Review Phase**: Use reviewer agent before merging
4. **Testing Phase**: Use test agent to ensure quality

---

## Tips for Best Results

1. **Be Specific**: Clear task descriptions help agents understand what you need
2. **Provide Context**: Mention relevant files, modules, or issues
3. **Iterate**: A good plan often goes through multiple iterations
4. **Ask for Alternatives**: Agents can suggest different approaches
5. **Use the Output**: Review the agent's output and ask follow-up questions

---

## File Structure

```
.claude/agents/
├── README.md          # This file
├── planner.md         # Planner agent definition
├── test-agent.md      # Test agent definition
└── reviewer.md        # Reviewer agent definition
```

---

## Getting Started

Try this workflow:

```bash
# Pick a feature you want to implement
@planner add email notifications for document uploads

# Review the plan
# (You can ask for clarifications)

# Implement the changes

# Review before merging
@reviewer review the notification implementation

# Add tests
@test-agent add tests for email notifications
```

Enjoy working with the multi-agent system! 🚀
