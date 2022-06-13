
gt_description = "Crustal C sensitivity w ids trimmed. AWS EC2 batch test."

logic_tree_permutations = [ 
    
    [{
        "tag": "b = 0.849: N = 3.03, C=4.1", "weight": 1.0,
        "permute" : [

            {   "group": "Hik",
                "members" : [
                    {"tag": "Hik TC, b1.067, C4.1, s0.75", "weight": 0.08333333333333333, "inv_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwNjQ2NA==", "bg_id":"RmlsZToxMDY1MzM="},
                    {"tag": "Hik TC, b1.067, C4.1, s1.0", "weight": 0.08333333333333333, "inv_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwNjQ2NQ==", "bg_id":"RmlsZToxMDY1NDA="},
                    {"tag": "Hik TC, b1.067, C4.1, s1.28", "weight": 0.08333333333333333, "inv_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwNjQ2Ng==", "bg_id":"RmlsZToxMDY1Mzg="},

                    {"tag": "Hik TC, b0.942, C4.0, s0.75", "weight": 0.08333333333333333, "inv_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwNjQ3MA==", "bg_id":"RmlsZToxMDY1MjY="},
                    {"tag": "Hik TC, b0.942, C4.0, s1.0", "weight": 0.08333333333333333, "inv_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwNjQ3MQ==", "bg_id":"RmlsZToxMDY1Mjk="},
                    {"tag": "Hik TC, b0.942, C4.0, s1.28", "weight": 0.08333333333333333, "inv_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwNjQ3Mg==", "bg_id":"RmlsZToxMDY1Mjc="},

                    {"tag": "Hik TL, b1.067, C4.1, s0.75", "weight": 0.08333333333333333, "inv_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwNjQ3OQ==", "bg_id":"RmlsZToxMDY1MzQ="},
                    {"tag": "Hik TL, b1.067, C4.1, s1.0", "weight": 0.08333333333333333, "inv_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwNjQ4MA==", "bg_id":"RmlsZToxMDY1Mzk="},
                    {"tag": "Hik TL, b1.067, C4.1, s1.28", "weight": 0.08333333333333333, "inv_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwNjQ4MQ==", "bg_id":"RmlsZToxMDY1Mzc="},

                    {"tag": "Hik TL, b0.942, C4.0, s0.75", "weight": 0.08333333333333333, "inv_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwNjQ4NQ==", "bg_id":"RmlsZToxMDY1MjU="},
                    {"tag": "Hik TL, b0.942, C4.0, s1.0", "weight": 0.08333333333333333, "inv_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwNjQ4Ng==", "bg_id":"RmlsZToxMDY1MzA="},
                    {"tag": "Hik TL, b0.942, C4.0, s1.28", "weight": 0.08333333333333333, "inv_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwNjQ4Nw==", "bg_id":"RmlsZToxMDY1Mjg="}
                ]
            },

            {   "group": "PUY",
                "members" : [
                    {"tag": "Puysegur b0.712, C3.9, s1.0", "weight": 1.0, "inv_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwNjQ5Mg==", "bg_id": "RmlsZToxMDY1NTQ="}
                ]
            },

            {   "group": "CRU",
                "members" : [
                     {"tag": "Crustal b0.849, C4.1, s1.0", "weight": 1.0, "inv_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwNjUwNg==", "bg_id": "RmlsZToxMDY1NTM="}
                ]
            }
        ]
    }],

    [{
        "tag": "b = 0.849: N = 3.03, C=4.2", "weight": 1.0,
        "permute" : [
            {   "group": "Hik",
                "members" : [
                    {"tag": "Hik TC, b1.067, C4.1, s0.75", "weight": 0.08333333333333333, "inv_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwNjQ2NA==", "bg_id":"RmlsZToxMDY1MzM="},
                    {"tag": "Hik TC, b1.067, C4.1, s1.0", "weight": 0.08333333333333333, "inv_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwNjQ2NQ==", "bg_id":"RmlsZToxMDY1NDA="},
                    {"tag": "Hik TC, b1.067, C4.1, s1.28", "weight": 0.08333333333333333, "inv_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwNjQ2Ng==", "bg_id":"RmlsZToxMDY1Mzg="},

                    {"tag": "Hik TC, b0.942, C4.0, s0.75", "weight": 0.08333333333333333, "inv_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwNjQ3MA==", "bg_id":"RmlsZToxMDY1MjY="},
                    {"tag": "Hik TC, b0.942, C4.0, s1.0", "weight": 0.08333333333333333, "inv_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwNjQ3MQ==", "bg_id":"RmlsZToxMDY1Mjk="},
                    {"tag": "Hik TC, b0.942, C4.0, s1.28", "weight": 0.08333333333333333, "inv_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwNjQ3Mg==", "bg_id":"RmlsZToxMDY1Mjc="},

                    {"tag": "Hik TL, b1.067, C4.1, s0.75", "weight": 0.08333333333333333, "inv_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwNjQ3OQ==", "bg_id":"RmlsZToxMDY1MzQ="},
                    {"tag": "Hik TL, b1.067, C4.1, s1.0", "weight": 0.08333333333333333, "inv_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwNjQ4MA==", "bg_id":"RmlsZToxMDY1Mzk="},
                    {"tag": "Hik TL, b1.067, C4.1, s1.28", "weight": 0.08333333333333333, "inv_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwNjQ4MQ==", "bg_id":"RmlsZToxMDY1Mzc="},

                    {"tag": "Hik TL, b0.942, C4.0, s0.75", "weight": 0.08333333333333333, "inv_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwNjQ4NQ==", "bg_id":"RmlsZToxMDY1MjU="},
                    {"tag": "Hik TL, b0.942, C4.0, s1.0", "weight": 0.08333333333333333, "inv_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwNjQ4Ng==", "bg_id":"RmlsZToxMDY1MzA="},
                    {"tag": "Hik TL, b0.942, C4.0, s1.28", "weight": 0.08333333333333333, "inv_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwNjQ4Nw==", "bg_id":"RmlsZToxMDY1Mjg="}
                ]
            },

            {   "group": "PUY",
                "members" : [
                    {"tag": "Puysegur b0.712, C3.9, s1.0", "weight": 1.0, "inv_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwNjQ5Mg==", "bg_id": "RmlsZToxMDY1NTQ="}
                ]
            },

            {   "group": "CRU",
                "members" : [
                     {"tag": "Crustal b0.849, C4.2, s1.0", "weight": 1.0, "inv_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwNjUwNA==", "bg_id": "RmlsZToxMDY1NTM="}
                ]
            }
        ]
    }],

    [{
        "tag": "b = 0.849: N = 3.03, C=4.3", "weight": 1.0,
        "permute" : [
            {   "group": "Hik",
                "members" : [
                    {"tag": "Hik TC, b1.067, C4.1, s0.75", "weight": 0.08333333333333333, "inv_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwNjQ2NA==", "bg_id":"RmlsZToxMDY1MzM="},
                    {"tag": "Hik TC, b1.067, C4.1, s1.0", "weight": 0.08333333333333333, "inv_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwNjQ2NQ==", "bg_id":"RmlsZToxMDY1NDA="},
                    {"tag": "Hik TC, b1.067, C4.1, s1.28", "weight": 0.08333333333333333, "inv_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwNjQ2Ng==", "bg_id":"RmlsZToxMDY1Mzg="},

                    {"tag": "Hik TC, b0.942, C4.0, s0.75", "weight": 0.08333333333333333, "inv_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwNjQ3MA==", "bg_id":"RmlsZToxMDY1MjY="},
                    {"tag": "Hik TC, b0.942, C4.0, s1.0", "weight": 0.08333333333333333, "inv_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwNjQ3MQ==", "bg_id":"RmlsZToxMDY1Mjk="},
                    {"tag": "Hik TC, b0.942, C4.0, s1.28", "weight": 0.08333333333333333, "inv_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwNjQ3Mg==", "bg_id":"RmlsZToxMDY1Mjc="},

                    {"tag": "Hik TL, b1.067, C4.1, s0.75", "weight": 0.08333333333333333, "inv_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwNjQ3OQ==", "bg_id":"RmlsZToxMDY1MzQ="},
                    {"tag": "Hik TL, b1.067, C4.1, s1.0", "weight": 0.08333333333333333, "inv_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwNjQ4MA==", "bg_id":"RmlsZToxMDY1Mzk="},
                    {"tag": "Hik TL, b1.067, C4.1, s1.28", "weight": 0.08333333333333333, "inv_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwNjQ4MQ==", "bg_id":"RmlsZToxMDY1Mzc="},

                    {"tag": "Hik TL, b0.942, C4.0, s0.75", "weight": 0.08333333333333333, "inv_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwNjQ4NQ==", "bg_id":"RmlsZToxMDY1MjU="},
                    {"tag": "Hik TL, b0.942, C4.0, s1.0", "weight": 0.08333333333333333, "inv_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwNjQ4Ng==", "bg_id":"RmlsZToxMDY1MzA="},
                    {"tag": "Hik TL, b0.942, C4.0, s1.28", "weight": 0.08333333333333333, "inv_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwNjQ4Nw==", "bg_id":"RmlsZToxMDY1Mjg="}
                ]
            },

            {   "group": "PUY",
                "members" : [
                    {"tag": "Puysegur b0.712, C3.9, s1.0", "weight": 1.0, "inv_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwNjQ5Mg==", "bg_id": "RmlsZToxMDY1NTQ="}
                ]
            },

            {   "group": "CRU",
                "members" : [
                    {"tag": "Crustal b0.849, C4.3, s1.0", "weight": 1.0, "inv_id": "SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwNjUxMQ==", "bg_id": "RmlsZToxMDY1NTM="}
                ]
            }

        ]
    }]
]