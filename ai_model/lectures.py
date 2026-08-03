LECTURES = {
    'algorithms_data_structures': {
        'lecture_id': 'algorithms_data_structures',
        'title': 'Algorithms and Data Structures',
        'icon': 'fa-code',
        'prompt_file': 'algorithms_data_structures.txt',
        'template': 'lecture_chat.html',
        'tip': 'Ask about sorting, searching, or data structures like hash tables. For networking or OS, try those lectures.',
        'off_topic': {
            'keywords': ['tcp', 'udp', 'ip', 'dns', 'routing', 'switching', 'network security', 'cable', 'coax', 'ethernet', 'wifi', 'protocol', 'process', 'memory management', 'file system', 'scheduling', 'virtualization'],
            'response': "This lecture focuses on Algorithms and Data Structures. Please ask about sorting, searching, or data structures like hash tables. For networking, try the Networking lecture, or for system processes, try Operating Systems."
        },
    },
    'networking': {
        'lecture_id': 'networking',
        'title': 'Networking',
        'icon': 'fa-network-wired',
        'prompt_file': 'networking.txt',
        'template': 'lecture_chat.html',
        'tip': 'Ask about TCP/IP, OSI model, routing, or network security. For data structures, try Algorithms and Data Structures.',
        'off_topic': {
            'keywords': ['hash table', 'array', 'linked list', 'tree', 'graph', 'sorting', 'searching', 'process', 'memory management', 'file system', 'scheduling', 'virtualization'],
            'response': "I specialize in Networking. Please ask about network protocols, layers, security, or troubleshooting. For data structures like hash tables, try the Algorithms and Data Structures lecture, or for system processes, try Operating Systems."
        },
    },
    'operating_systems': {
        'lecture_id': 'operating_systems',
        'title': 'Operating Systems',
        'icon': 'fa-server',
        'prompt_file': 'operating_systems.txt',
        'template': 'lecture_chat.html',
        'tip': 'Ask about processes, memory management, or scheduling. For networking, try Networking.',
        'off_topic': {
            'keywords': ['hash table', 'array', 'linked list', 'tree', 'graph', 'sorting', 'searching', 'tcp', 'udp', 'ip', 'dns', 'routing', 'switching', 'network security', 'cable', 'coax', 'ethernet', 'wifi', 'protocol'],
            'response': "I specialize in Operating Systems. Please ask about processes, memory management, or file systems. For networking topics, try the Networking lecture, or for data structures, try Algorithms and Data Structures."
        },
    },
}