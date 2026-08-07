    node.querySelector(".up").addEventListener("click", async (e) => {
      e.target.disabled = true;
      try {
        await submitRating(paper.id, 1);
        card.remove();
        maybeShowEmpty();
      } catch (err) {
        alert("Rating failed: " + err.message);
        e.target.disabled = false;
      }
    });
    node.querySelector(".down").addEventListener("click", async (e) => {
      e.target.disabled = true;
      try {
        await submitRating(paper.id, -1);
        card.remove();
        maybeShowEmpty();
      } catch (err) {
        alert("Rating failed: " + err.message);
        e.target.disabled = false;
      }
    });
