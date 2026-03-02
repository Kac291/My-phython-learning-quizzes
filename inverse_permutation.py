def inverse_perm(L):
    space = set()
    dic = {}
    for i in range(len(L)):
        if L[i] in space:
            return {}
        elif L[i] < 0:
            return {}
        elif L[i] > len(L) - 1:
            return {}
        space.add(L[i])
        dic[L[i]] = i
    return dic


if __name__ == "__main__":
    print("测试 [2, 0, 1]:", inverse_perm([2, 0, 1]))
    print("测试 [1, 1, 0]:", inverse_perm([1, 1, 0]))
