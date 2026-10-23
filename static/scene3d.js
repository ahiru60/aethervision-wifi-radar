// AetherVision // 3D Volumetric RF Wave & Holographic Room Visualizer
// Powered by Three.js

class RFScene3D {
  constructor(containerElement) {
    this.container = containerElement;
    this.width = Math.max(100, this.container.clientWidth || 800);
    this.height = Math.max(100, this.container.clientHeight || 380);
    
    this.scene = null;
    this.camera = null;
    this.renderer = null;
    this.controls = null;
    
    // RF Simulation Objects
    this.fresnelMesh = null;
    this.fresnelOriginalPositions = null;
    this.particles = null;
    this.particleCount = 1200;
    this.particlePositions = null;
    this.particleColors = null;
    this.particleVelocities = null;
    this.routerWaveRings = [];
    this.targetEchoGroup = null;
    
    // State
    this.perturbation = 0.0;
    this.jitter = 0.0;
    this.motionState = "STATIC";
    this.clock = new THREE.Clock();
    
    try {
      this.init();
      console.log("[AetherVision] 3D WebGL Scene initialized successfully.");
    } catch (err) {
      console.error("[AetherVision] 3D initialization error:", err);
    }
  }

  init() {
    // 1. Scene
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0x060c18);
    this.scene.fog = new THREE.FogExp2(0x060c18, 0.015);

    // 2. Camera
    this.camera = new THREE.PerspectiveCamera(50, this.width / this.height, 0.1, 100);
    this.camera.position.set(6.0, 5.0, 6.5);
    this.camera.lookAt(0, 1.2, 0);

    // 3. Renderer
    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    this.renderer.setSize(this.width, this.height);
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    this.container.appendChild(this.renderer.domElement);

    // 4. Orbit Controls (Safe check)
    if (THREE.OrbitControls) {
      this.controls = new THREE.OrbitControls(this.camera, this.renderer.domElement);
      this.controls.enableDamping = true;
      this.controls.dampingFactor = 0.08;
      this.controls.maxPolarAngle = Math.PI / 2 - 0.05;
      this.controls.minDistance = 2;
      this.controls.maxDistance = 30;
      this.controls.target.set(0, 1.2, 0);
    }

    // 5. Lighting
    const hemiLight = new THREE.HemisphereLight(0x00f0ff, 0x0f172a, 1.4);
    this.scene.add(hemiLight);

    const dirLight = new THREE.DirectionalLight(0x00f0ff, 1.0);
    dirLight.position.set(5, 10, 5);
    this.scene.add(dirLight);

    // 6. Build Scene Objects
    this.createRoomEnvironment();
    this.createStations();
    this.createFresnelEllipsoid();
    this.createRFParticleField();
    this.createTargetEchoMarker();

    // 7. Handle Resize
    window.addEventListener('resize', () => this.onResize());

    // 8. Animation Loop
    this.animate = this.animate.bind(this);
    requestAnimationFrame(this.animate);
  }

  createRoomEnvironment() {
    // Room dimensions: 10m x 7m x 4m
    const roomW = 10, roomD = 7, roomH = 3.5;

    // Floor Grid with Cyber aesthetic
    const gridHelper = new THREE.GridHelper(12, 24, 0x00f0ff, 0x142840);
    gridHelper.position.y = 0;
    this.scene.add(gridHelper);

    // Tactical Room Perimeter Boundary Box (Wireframe)
    const boxGeo = new THREE.BoxGeometry(roomW, roomH, roomD);
    const boxEdges = new THREE.EdgesGeometry(boxGeo);
    const boxMat = new THREE.LineBasicMaterial({
      color: 0x00f0ff,
      transparent: true,
      opacity: 0.15
    });
    const roomBounds = new THREE.LineSegments(boxEdges, boxMat);
    roomBounds.position.y = roomH / 2;
    this.scene.add(roomBounds);

    // Glowing Room Corner Brackets
    this.createCornerBrackets(roomW, roomH, roomD);
  }

  createCornerBrackets(w, h, d) {
    const bracketMat = new THREE.LineBasicMaterial({ color: 0x00f0ff, transparent: true, opacity: 0.6 });
    const s = 0.5; // bracket size
    const corners = [
      [-w/2, 0, -d/2], [w/2, 0, -d/2], [-w/2, 0, d/2], [w/2, 0, d/2],
      [-w/2, h, -d/2], [w/2, h, -d/2], [-w/2, h, d/2], [w/2, h, d/2]
    ];

    corners.forEach(([cx, cy, cz]) => {
      const signX = cx > 0 ? -1 : 1;
      const signY = cy > 0 ? -1 : 1;
      const signZ = cz > 0 ? -1 : 1;

      const points = [
        new THREE.Vector3(cx, cy, cz), new THREE.Vector3(cx + signX * s, cy, cz),
        new THREE.Vector3(cx, cy, cz), new THREE.Vector3(cx, cy + signY * s, cz),
        new THREE.Vector3(cx, cy, cz), new THREE.Vector3(cx, cy, cz + signZ * s)
      ];
      const geo = new THREE.BufferGeometry().setFromPoints(points);
      const line = new THREE.LineSegments(geo, bracketMat);
      this.scene.add(line);
    });
  }

  createStations() {
    // TX ROUTER STATION (Left side: X = -3.8)
    const txGroup = new THREE.Group();
    txGroup.position.set(-3.8, 0, 0);

    // Pedestal
    const pedGeo = new THREE.CylinderGeometry(0.3, 0.4, 1.0, 16);
    const pedMat = new THREE.MeshStandardMaterial({ color: 0x0f172a, roughness: 0.7 });
    const ped = new THREE.Mesh(pedGeo, pedMat);
    ped.position.y = 0.5;
    txGroup.add(ped);

    // Router Body
    const rBodyGeo = new THREE.BoxGeometry(0.6, 0.1, 0.4);
    const rBodyMat = new THREE.MeshStandardMaterial({ color: 0x1e293b, roughness: 0.3 });
    const routerBody = new THREE.Mesh(rBodyGeo, rBodyMat);
    routerBody.position.y = 1.05;
    txGroup.add(routerBody);

    // Dual Antennas
    [-0.2, 0.2].forEach(ax => {
      const antGeo = new THREE.CylinderGeometry(0.015, 0.015, 0.45, 8);
      const antMat = new THREE.MeshBasicMaterial({ color: 0xff0055 });
      const ant = new THREE.Mesh(antGeo, antMat);
      ant.position.set(ax, 1.25, 0.1);
      txGroup.add(ant);
    });

    // Glowing Transmitter LED
    const ledGeo = new THREE.SphereGeometry(0.04, 12, 12);
    const ledMat = new THREE.MeshBasicMaterial({ color: 0xff0055 });
    const led = new THREE.Mesh(ledGeo, ledMat);
    led.position.set(0, 1.12, 0.18);
    txGroup.add(led);

    this.scene.add(txGroup);

    // Expanding 3D Spherical Waves from Router
    for (let i = 0; i < 3; i++) {
      const waveGeo = new THREE.SphereGeometry(1, 24, 24);
      const waveMat = new THREE.MeshBasicMaterial({
        color: 0xff0055,
        wireframe: true,
        transparent: true,
        opacity: 0.15
      });
      const waveMesh = new THREE.Mesh(waveGeo, waveMat);
      waveMesh.position.set(-3.8, 1.2, 0);
      this.scene.add(waveMesh);
      this.routerWaveRings.push({ mesh: waveMesh, offset: i * 0.33 });
    }

    // RX LAPTOP STATION (Right side: X = +3.8)
    const rxGroup = new THREE.Group();
    rxGroup.position.set(3.8, 0, 0);

    const ped2 = new THREE.Mesh(pedGeo, pedMat);
    ped2.position.y = 0.5;
    rxGroup.add(ped2);

    // Laptop Base
    const lapBaseGeo = new THREE.BoxGeometry(0.7, 0.03, 0.5);
    const lapBaseMat = new THREE.MeshStandardMaterial({ color: 0x334155, roughness: 0.4 });
    const lapBase = new THREE.Mesh(lapBaseGeo, lapBaseMat);
    lapBase.position.y = 1.02;
    rxGroup.add(lapBase);

    // Laptop Screen
    const lapScreenGeo = new THREE.BoxGeometry(0.68, 0.45, 0.02);
    const lapScreenMat = new THREE.MeshBasicMaterial({ color: 0x00f0ff });
    const lapScreen = new THREE.Mesh(lapScreenGeo, lapScreenMat);
    lapScreen.position.set(0, 1.24, -0.22);
    lapScreen.rotation.x = -0.15;
    rxGroup.add(lapScreen);

    this.scene.add(rxGroup);
  }

  createFresnelEllipsoid() {
    // In physics, 1st Fresnel Zone is a prolate spheroid between TX (-3.8) and RX (+3.8)
    // Distance = 7.6m. Center = (0, 1.2, 0)
    // Semi-major axis = 3.8m + margin, Semi-minor axes = ~1.2m
    const sphereGeo = new THREE.SphereGeometry(1, 32, 24);
    
    // Scale into prolate spheroid
    sphereGeo.scale(3.9, 1.3, 1.3);

    const fresnelMat = new THREE.MeshBasicMaterial({
      color: 0x00f0ff,
      wireframe: true,
      transparent: true,
      opacity: 0.22
    });

    this.fresnelMesh = new THREE.Mesh(sphereGeo, fresnelMat);
    this.fresnelMesh.position.set(0, 1.2, 0);
    this.scene.add(this.fresnelMesh);

    // Cache original vertex positions for dynamic perturbation warping
    const pos = sphereGeo.attributes.position;
    this.fresnelOriginalPositions = new Float32Array(pos.array.length);
    this.fresnelOriginalPositions.set(pos.array);
  }

  createRFParticleField() {
    // 1200 glowing particles flowing along the RF line of sight and reflections
    const count = this.particleCount;
    const geometry = new THREE.BufferGeometry();
    
    this.particlePositions = new Float32Array(count * 3);
    this.particleColors = new Float32Array(count * 3);
    this.particleVelocities = new Float32Array(count * 3);

    const baseColor = new THREE.Color(0x00f0ff);

    for (let i = 0; i < count; i++) {
      const idx = i * 3;
      // Scatter along the X-axis from -3.8 to +3.8 with Gaussian spread in Y and Z
      const u = Math.random();
      const x = -3.8 + u * 7.6;
      
      // Radius of Fresnel zone at distance x
      const normX = (x / 3.8); // -1 to 1
      const maxR = Math.sqrt(Math.max(0, 1 - normX * normX)) * 1.3;
      
      const angle = Math.random() * Math.PI * 2;
      const r = Math.pow(Math.random(), 0.6) * maxR;

      this.particlePositions[idx] = x;
      this.particlePositions[idx + 1] = 1.2 + Math.sin(angle) * r;
      this.particlePositions[idx + 2] = Math.cos(angle) * r;

      this.particleVelocities[idx] = 1.5 + Math.random() * 2.0; // speed towards laptop
      this.particleVelocities[idx + 1] = (Math.random() - 0.5) * 0.2;
      this.particleVelocities[idx + 2] = (Math.random() - 0.5) * 0.2;

      this.particleColors[idx] = baseColor.r;
      this.particleColors[idx + 1] = baseColor.g;
      this.particleColors[idx + 2] = baseColor.b;
    }

    geometry.setAttribute('position', new THREE.BufferAttribute(this.particlePositions, 3));
    geometry.setAttribute('color', new THREE.BufferAttribute(this.particleColors, 3));

    // Custom circle particle texture
    const particleMat = new THREE.PointsMaterial({
      size: 0.12,
      vertexColors: true,
      transparent: true,
      opacity: 0.85,
      blending: THREE.AdditiveBlending
    });

    this.particles = new THREE.Points(geometry, particleMat);
    this.scene.add(this.particles);
  }

  createTargetEchoMarker() {
    // 3D Holographic marker that lights up when someone steps into the field
    this.targetEchoGroup = new THREE.Group();
    this.targetEchoGroup.position.set(0, 0, 0);
    this.targetEchoGroup.visible = false;

    // Vertical Scanner Beacon Line
    const lineGeo = new THREE.BufferGeometry().setFromPoints([
      new THREE.Vector3(0, 0, 0),
      new THREE.Vector3(0, 2.2, 0)
    ]);
    const lineMat = new THREE.LineBasicMaterial({ color: 0xffbe0b, transparent: true, opacity: 0.7 });
    const line = new THREE.Line(lineGeo, lineMat);
    this.targetEchoGroup.add(line);

    // Concentric Target Rings
    [0.4, 0.7].forEach(rad => {
      const ringGeo = new THREE.RingGeometry(rad - 0.03, rad, 32);
      const ringMat = new THREE.MeshBasicMaterial({
        color: 0xffbe0b,
        side: THREE.DoubleSide,
        transparent: true,
        opacity: 0.6
      });
      const ring = new THREE.Mesh(ringGeo, ringMat);
      ring.rotation.x = Math.PI / 2;
      ring.position.y = 0.05;
      this.targetEchoGroup.add(ring);
    });

    // Holographic Humanoid Silhouette / Scatterer Wireframe
    const torsoGeo = new THREE.CylinderGeometry(0.18, 0.12, 0.9, 12, 3, true);
    const torsoMat = new THREE.MeshBasicMaterial({ color: 0xff0055, wireframe: true, transparent: true, opacity: 0.5 });
    const torso = new THREE.Mesh(torsoGeo, torsoMat);
    torso.position.y = 1.1;
    this.targetEchoGroup.add(torso);

    const headGeo = new THREE.SphereGeometry(0.12, 12, 12);
    const headMat = new THREE.MeshBasicMaterial({ color: 0xff0055, wireframe: true, transparent: true, opacity: 0.6 });
    const head = new THREE.Mesh(headGeo, headMat);
    head.position.y = 1.7;
    this.targetEchoGroup.add(head);

    this.scene.add(this.targetEchoGroup);
  }

  updateData(sensing, telemetry) {
    if (!sensing) return;
    this.perturbation = sensing.perturbation_index || 0.0;
    this.jitter = sensing.rtt_jitter_ms || 0.0;
    this.motionState = sensing.motion_state || "STATIC";
  }

  animate() {
    requestAnimationFrame(this.animate);
    const dt = this.clock.getDelta();
    const t = this.clock.getElapsedTime();

    this.controls.update();

    // 1. Animate Router Wavefronts
    this.routerWaveRings.forEach(item => {
      const progress = ((t * 0.8 + item.offset) % 1.0);
      const scale = 0.2 + progress * 4.5;
      item.mesh.scale.set(scale, scale, scale);
      item.mesh.material.opacity = Math.max(0, (1 - progress) * 0.2);
    });

    // 2. Animate and Warp 3D Fresnel Ellipsoid
    if (this.fresnelMesh && this.fresnelOriginalPositions) {
      const posAttr = this.fresnelMesh.geometry.attributes.position;
      const arr = posAttr.array;
      const orig = this.fresnelOriginalPositions;
      const perturb = this.perturbation;

      const warpMag = perturb > 15 ? (perturb / 100.0) * 0.45 : 0.04;

      for (let i = 0; i < arr.length; i += 3) {
        const ox = orig[i];
        const oy = orig[i + 1];
        const oz = orig[i + 2];

        // Wave ripple distortion across the ellipsoid
        const ripple = Math.sin(ox * 4.0 - t * 6.0) * Math.cos(oy * 3.0 + t * 4.0) * warpMag;
        arr[i] = ox + (ox / 3.9) * ripple;
        arr[i + 1] = oy + (oy / 1.3) * ripple;
        arr[i + 2] = oz + (oz / 1.3) * ripple;
      }
      posAttr.needsUpdate = true;

      // Color transition of Fresnel zone
      if (perturb > 35) {
        this.fresnelMesh.material.color.setHex(0xff0055);
        this.fresnelMesh.material.opacity = 0.45;
      } else if (perturb > 15) {
        this.fresnelMesh.material.color.setHex(0xffbe0b);
        this.fresnelMesh.material.opacity = 0.3;
      } else {
        this.fresnelMesh.material.color.setHex(0x00f0ff);
        this.fresnelMesh.material.opacity = 0.2;
      }
    }

    // 3. Animate RF Particles
    if (this.particles) {
      const pos = this.particlePositions;
      const col = this.particleColors;
      const vel = this.particleVelocities;
      const count = this.particleCount;
      const perturb = this.perturbation;

      // Color targets
      const cyan = { r: 0.0, g: 0.94, b: 1.0 };
      const amber = { r: 1.0, g: 0.75, b: 0.04 };
      const red = { r: 1.0, g: 0.0, b: 0.33 };

      const targetCol = perturb > 35 ? red : (perturb > 15 ? amber : cyan);

      for (let i = 0; i < count; i++) {
        const idx = i * 3;
        
        // Advance particle towards laptop
        pos[idx] += vel[idx] * dt;

        // Add perturbation turbulence if room is disturbed
        if (perturb > 15) {
          const turb = (perturb / 100.0) * 0.8;
          pos[idx + 1] += (Math.sin(pos[idx] * 5.0 + t * 10.0) * turb) * dt;
          pos[idx + 2] += (Math.cos(pos[idx] * 5.0 - t * 8.0) * turb) * dt;
        }

        // Reset if reached laptop (+3.8)
        if (pos[idx] >= 3.8) {
          pos[idx] = -3.8;
          const u = Math.random();
          const angle = Math.random() * Math.PI * 2;
          const r = Math.pow(Math.random(), 0.6) * 1.2;
          pos[idx + 1] = 1.2 + Math.sin(angle) * r;
          pos[idx + 2] = Math.cos(angle) * r;
        }

        // Smooth color interpolation
        col[idx] += (targetCol.r - col[idx]) * 0.1;
        col[idx + 1] += (targetCol.g - col[idx + 1]) * 0.1;
        col[idx + 2] += (targetCol.b - col[idx + 2]) * 0.1;
      }

      this.particles.geometry.attributes.position.needsUpdate = true;
      this.particles.geometry.attributes.color.needsUpdate = true;
    }

    // 4. Update Target Intrusion Phantom Marker
    if (this.targetEchoGroup) {
      if (this.perturbation > 22.0) {
        this.targetEchoGroup.visible = true;
        // Position echo near the midpoint with slight Doppler drift
        const wobbleX = Math.sin(t * 1.5) * 0.6;
        const wobbleZ = Math.cos(t * 1.2) * 0.8;
        this.targetEchoGroup.position.set(wobbleX, 0, wobbleZ);
        this.targetEchoGroup.rotation.y += 0.02;
      } else {
        this.targetEchoGroup.visible = false;
      }
    }

    this.renderer.render(this.scene, this.camera);
  }

  setCameraPreset(preset) {
    if (!this.camera) return;
    switch (preset) {
      case 'isometric':
        this.camera.position.set(6.5, 7.0, 7.5);
        if (this.controls) this.controls.target.set(0, 1.2, 0);
        break;
      case 'top':
        this.camera.position.set(0.01, 13.0, 0.01);
        if (this.controls) this.controls.target.set(0, 0, 0);
        break;
      case 'los':
        // Behind router looking directly down microwave beam at laptop
        this.camera.position.set(-6.5, 1.3, 0);
        if (this.controls) this.controls.target.set(3.8, 1.2, 0);
        break;
    }
  }

  onResize() {
    if (!this.container || !this.renderer || !this.camera) return;
    this.width = this.container.clientWidth;
    this.height = this.container.clientHeight;
    this.camera.aspect = this.width / this.height;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(this.width, this.height);
  }
}

window.RFScene3D = RFScene3D;
