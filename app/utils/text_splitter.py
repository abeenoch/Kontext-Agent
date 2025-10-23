def split_text(text, chunk_size=800, overlap=100):
   words = text.split()
   chunks = []
   i =0
   while i < len(words):
        chunk = words[i:i+chunk_size]
        chunks.append(" ".join(chunk))
        i += chunk_size - overlap   
        return chunks

