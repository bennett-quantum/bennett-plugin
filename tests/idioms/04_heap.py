"""N malloc sites form a list or a binary tree, then recursive traversal."""
from common import options, emit
n, v = options('list')
parts = ['struct Node { struct Node *left, *right; unsigned value; };',
         'static NO unsigned visit(struct Node *p) {',
         'if (!p) return 0;',
         'return p->value + visit(p->left) + visit(p->right); }',
         'int main(void) {']
for i in range(n):
    parts += [f'struct Node *p{i} = malloc(sizeof(struct Node));',
              f'if (!p{i}) return 1; p{i}->value = seed + {i};',
              f'p{i}->left = 0; p{i}->right = 0;']
for i in range(n):
    if v == 'list' and i+1 < n:
        parts += [f'p{i}->left = p{i+1};']
    if v == 'tree':
        for field, j in [('left', 2*i+1), ('right', 2*i+2)]:
            if j < n:
                parts += [f'p{i}->{field} = p{j};']
parts += ['unsigned x=visit(p0); sink=x; return x&255; }']
emit(parts)
