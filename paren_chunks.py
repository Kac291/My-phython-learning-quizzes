def paren_chunks(s):
    L = []
    if len(s) == 0:
        return []
    if s[0] == ')':
        return []
    t = ''
    c = 0
    d = 0
    for o in range(len(s)):
        if s[o] == '(':
            c += 1
            t += s[o]
        if s[o] == ')':
            d += 1
            t += s[o]
        if d > c:
            return []
        if c == d:
            c = 0
            d = 0
            L.append(t)
            t = ''
    if c != d:
        return []
    return   
if __name__ == "__main__":
    print("--- 括号切片测试 ---")
    
    # 测试 1: 简单的平铺括号
    print("测试 '()()':", paren_chunks("()()")) 
    
    # 测试 2: 嵌套括号
    print("测试 '(())()':", paren_chunks("(())()")) 
    
    # 测试 3: 只有左括号（非法）
    print("测试 '(((': ", paren_chunks("(((")) 
    
    # 测试 4: 右括号开头（非法）
    print("测试 ')()(': ", paren_chunks(")()(")) 
    
    # 测试 5: 复杂的混合嵌套
    print("测试 '(()())((()))':", paren_chunks("(()())((()))"))
