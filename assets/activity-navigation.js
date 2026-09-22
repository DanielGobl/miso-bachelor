'use strict';

function createActivityNavigation(activities, isUnlocked) {
  const byId = id => document.getElementById(id);
  const directions = destination => `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(destination)}&dir_action=navigate`;
  const locations = [
    {
      address: 'Wybrzeże Kościuszkowskie 20, 00-390 Warszawa',
      mapsUrl: directions('Centrum Nauki Kopernik, Wybrzeże Kościuszkowskie 20, 00-390 Warszawa')
    },
    {
      address: 'Miami Wars\nSolec 8, 00-439 Warszawa',
      mapsUrl: directions('Miami Wars, Solec 8, 00-439 Warszawa')
    },
    {
      address: 'Boisko Archery Games, Al. 3 Maja, Warszawa',
      mapsUrl: 'https://maps.app.goo.gl/SnPpvK2UPu3bSVFt8'
    },
    {
      address: 'Miesto stretnutia: 52.240950, 21.011296',
      mapsUrl: directions('52.240950, 21.011296')
    }
  ];

  function sync() {
    locations.forEach((location, index) => {
      const destination = byId(activities[index].destination);
      const existing = destination.querySelector('.activity-navigation');
      if (!isUnlocked(index)) {
        existing?.remove();
        return;
      }
      if (!existing) {
        const block = document.createElement('div');
        block.className = 'activity-navigation';
        const address = document.createElement('p');
        address.textContent = `📍 ${location.address}`;
        const link = document.createElement('a');
        link.className = 'ops-button';
        link.textContent = '🧭 NAVIGOVAŤ NA MIESTO';
        link.href = location.mapsUrl;
        link.target = '_blank';
        link.rel = 'noopener noreferrer';
        block.append(address, link);
        destination.append(block);
      }
    });
  }

  return { sync };
}
